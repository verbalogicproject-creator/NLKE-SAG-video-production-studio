from __future__ import annotations

import os
import importlib.util
import hmac
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .commands import CommandService
from .capabilities import detect_capabilities
from .contracts import COMMAND_REGISTRY, declared_commands
from .media import MediaIntakeError, MediaService
from .models import (
    CommandRequest,
    CommandValidationError,
    ObservationContract,
    ObservationResult,
    PairAttachRequest,
    PairStartRequest,
    MediaImportResult,
    ProjectCreateRequest,
    Receipt,
    ReceiptStatus,
    RenderRequest,
    SelectionRequest,
    ShortsGenerateRequest,
    SuggestionDecisionRequest,
    StaleRevisionError,
)
from .rendering import RenderService, RenderValidationError, RenderWorker
from .shorts import AnalysisWorker, ShortsError, ShortsService, providers_from_env
from .store import Store


@dataclass(frozen=True)
class Settings:
    database_path: str = ".sag-video/sag-video.db"
    artifact_dir: str = ".sag-video/artifacts"
    media_dir: str = ".sag-video/media"
    proxy_dir: str = ".sag-video/proxies"
    upload_limit_bytes: int = 512 * 1024 * 1024
    invite_token: str = ""
    observer_url: str = ""
    start_analysis_worker: bool = True
    service_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=os.getenv("SAG_VIDEO_DATABASE_PATH", cls.database_path),
            artifact_dir=os.getenv("SAG_VIDEO_ARTIFACT_DIR", cls.artifact_dir),
            media_dir=os.getenv("SAG_VIDEO_MEDIA_DIR", cls.media_dir),
            proxy_dir=os.getenv("SAG_VIDEO_PROXY_DIR", cls.proxy_dir),
            upload_limit_bytes=int(os.getenv("SAG_VIDEO_UPLOAD_LIMIT_BYTES", str(cls.upload_limit_bytes))),
            invite_token=os.getenv("SAG_VIDEO_INVITE_TOKEN", ""),
            observer_url=os.getenv("SAG_VIDEO_OBSERVER_URL", ""),
            start_analysis_worker=os.getenv("SAG_VIDEO_START_ANALYSIS_WORKER", "1").lower() not in {"0", "false", "no"},
            service_token=os.getenv("SAG_VIDEO_SERVICE_TOKEN", ""),
        )


def _remote_observer(url: str):
    def observe(contract: ObservationContract) -> ObservationResult:
        response = httpx.post(
            f"{url.rstrip('/')}/observe",
            json={"contract": contract.model_dump(mode="json")},
            timeout=45,
        )
        response.raise_for_status()
        return ObservationResult.model_validate(response.json())

    return observe


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    static_dir = Path(__file__).parent / "static"
    artifact_dir = Path(settings.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.database_path)
    commands = CommandService(store)
    capabilities = detect_capabilities()
    media = MediaService(
        store,
        settings.media_dir,
        settings.proxy_dir,
        upload_limit_bytes=settings.upload_limit_bytes,
    )
    renderer = RenderService(
        store,
        artifact_dir,
        media.path_for_asset,
        observer=_remote_observer(settings.observer_url) if settings.observer_url else __import__(
            "sag_video.observer", fromlist=["observe_artifact"]
        ).observe_artifact,
    )
    worker = RenderWorker(store, renderer)
    transcriber, ranker = providers_from_env()
    capabilities["shorts"] = {
        "transcription": transcriber.capabilities(),
        "ranking": {"configured": ranker is not None, "provider": getattr(ranker, "id", None)},
        "face_tracking": {
            "provider": "mediapipe", "optional": True,
            "available": importlib.util.find_spec("mediapipe") is not None and importlib.util.find_spec("cv2") is not None,
        },
        "languages": ["en", "he"],
        "default_candidate_count": 5,
        "duration_seconds": {"minimum": 15, "preferred": [30, 60], "maximum": 90},
    }
    shorts = ShortsService(store, media.path_for_asset, transcriber, ranker)
    analysis_worker = AnalysisWorker(store, shorts)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker.start()
        if settings.start_analysis_worker:
            analysis_worker.start()
        try:
            yield
        finally:
            worker.stop()
            analysis_worker.stop()
            store.close()

    application = FastAPI(title="SAG Video", version="0.1.0", lifespan=lifespan)
    application.state.store = store
    application.state.commands = commands
    application.state.media = media
    application.state.capabilities = capabilities
    application.state.renderer = renderer
    application.state.render_worker = worker
    application.state.shorts = shorts
    application.state.analysis_worker = analysis_worker
    application.state.settings = settings

    def _require_workspace(request: Request, project_id: str) -> None:
        workspace_id = getattr(request.state, "workspace_id", None)
        if workspace_id not in {None, "*"} and not store.project_in_workspace(project_id, workspace_id):
            raise HTTPException(403, "paired token is scoped to another workspace")

    def _require_unscoped(request: Request) -> None:
        if getattr(request.state, "service_authenticated", False):
            return
        workspace_id = getattr(request.state, "workspace_id", None)
        if workspace_id not in {None, "*"}:
            raise HTTPException(403, "paired project token cannot create projects")

    @application.middleware("http")
    async def invite_gate(request: Request, call_next):
        service_header = request.headers.get("x-sag-service-token", "")
        if settings.service_token and hmac.compare_digest(service_header, settings.service_token):
            workspace_id = request.headers.get("x-sag-workspace-id", "").strip()
            if not workspace_id:
                return JSONResponse({"detail": "x-sag-workspace-id is required", "code": "workspace_required"}, status_code=400)
            request.state.actor = "verbalogix-orchestrator"
            request.state.workspace_id = workspace_id
            request.state.service_authenticated = True
            return await call_next(request)
        if request.url.path in {"/", "/health", "/api/pairing/attach"} or request.url.path.startswith("/static/"):
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        bearer = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        principal = store.principal_for_token(bearer) if bearer else None
        if principal:
            request.state.actor = principal["actor_name"]
            request.state.workspace_id = principal["workspace_id"]
        if not settings.invite_token:
            return await call_next(request)

        supplied = request.headers.get("x-invite-token")
        browser_cookie = request.cookies.get("sag_video_session", "")
        browser_principal = store.principal_for_token(browser_cookie) if browser_cookie else None
        invite_valid = supplied == settings.invite_token or (browser_principal and browser_principal["actor_name"] == "browser")
        if not invite_valid and principal is None:
            return JSONResponse({"detail": "invite or paired terminal token required"}, status_code=401)
        response = await call_next(request)
        if supplied == settings.invite_token and not (browser_principal and browser_principal["actor_name"] == "browser"):
            session_token, _ = store.issue_token("*", "browser")
            response.set_cookie(
                "sag_video_session",
                session_token,
                max_age=8 * 60 * 60,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
            )
        return response

    @application.exception_handler(StaleRevisionError)
    async def stale_revision_handler(_: Request, error: StaleRevisionError):
        return JSONResponse(
            {"detail": str(error), "code": "stale_revision", "expected_revision": error.expected, "current_revision": error.actual},
            status_code=409,
        )

    @application.exception_handler(CommandValidationError)
    async def command_validation_handler(_: Request, error: CommandValidationError):
        return JSONResponse({"detail": str(error), "code": "invalid_command_arguments"}, status_code=422)

    @application.exception_handler(MediaIntakeError)
    async def media_intake_handler(_: Request, error: MediaIntakeError):
        return JSONResponse({"detail": str(error), "code": "media_intake_rejected"}, status_code=415)

    @application.exception_handler(RenderValidationError)
    async def render_validation_handler(_: Request, error: RenderValidationError):
        return JSONResponse({"detail": str(error), "code": "render_spec_rejected"}, status_code=422)

    @application.exception_handler(ShortsError)
    async def shorts_error_handler(_: Request, error: ShortsError):
        return JSONResponse({"detail": str(error), "code": "shorts_request_rejected"}, status_code=422)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "sag-video-control", "version": "0.1.0"}

    @application.get("/api/capabilities")
    def get_capabilities() -> dict:
        return capabilities

    @application.get("/api/contract")
    def get_contract(http_request: Request) -> dict:
        actor = getattr(http_request.state, "actor", "browser")
        return {
            "application": {"id": "sag-video", "name": "SAG Video", "contract_version": "0.1", "protocol_versions": ["sag-http-0.1"]},
            "entities": {
                "workspace": {"identity": "stable workspace.id containing source and derived projects"},
                "project": {"identity": "stable project.id"},
                "asset": {"identity": "stable asset.id scoped to a project"},
                "timeline_item": {"identity": "stable timeline item.id scoped to a project"},
                "receipt": {"identity": "stable causal receipt.id"},
                "job": {"identity": "stable persistent job.id"},
                "artifact": {"identity": "stable observed artifact.id scoped to a project"},
                "analysis_artifact": {"identity": "immutable provider-and-settings-versioned analysis.id"},
                "suggestion": {"identity": "stable auditable suggestion.id tied to an exact source revision"},
            },
            "commands": declared_commands(),
            "authority": {
                "actor": actor,
                "declared_required_scopes": sorted({entry.required_scope for entry in COMMAND_REGISTRY.values()}),
                "context_grants_authority": False,
                "note": "The server evaluates actual authentication, revision, target, and arguments on every invocation.",
            },
            "receipts": {
                "dispatch_is_success": False,
                "terminal_states": ["observed_success", "observed_failure", "execution_failed", "denied", "cancelled", "timeout"],
                "render_nonterminal_states": ["accepted", "dispatched", "rendering", "artifact_written", "awaiting_observation"],
            },
            "capabilities": capabilities,
        }

    @application.get("/api/projects")
    def list_projects(http_request: Request) -> dict:
        workspace_id = getattr(http_request.state, "workspace_id", None)
        return {
            "projects": [
                {
                    "id": project.id,
                    "name": project.name,
                    "revision": project.revision,
                    "schema_version": project.schema_version,
                    "canvas": project.canvas.model_dump(mode="json"),
                    "updated_at": project.updated_at,
                }
                for project in (
                    store.list_projects() if workspace_id in {None, "*"}
                    else store.list_projects_for_workspace(workspace_id)
                )
            ]
        }

    @application.post("/api/projects")
    def create_project(request: ProjectCreateRequest, http_request: Request) -> dict:
        _require_unscoped(http_request)
        scoped_workspace = getattr(http_request.state, "workspace_id", None)
        if getattr(http_request.state, "service_authenticated", False) and request.workspace_id not in {None, scoped_workspace}:
            raise HTTPException(403, "workspace body does not match service scope")
        project = store.create_project(request.name, request.preset, scoped_workspace if scoped_workspace not in {None, "*"} else request.workspace_id)
        return {"project": project.model_dump(mode="json"), "selection": []}

    @application.get("/api/projects/{project_id}")
    def get_project(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            project = store.get_project(project_id)
        except KeyError as error:
            raise HTTPException(404, "project not found") from error
        return {"project": project.model_dump(mode="json"), "selection": store.get_selection(project_id)}

    @application.get("/api/projects/{project_id}/context")
    def get_context(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            project = store.get_project(project_id)
            selected_ids = store.get_selection(project_id)
            selected = []
            for item_id in selected_ids:
                try:
                    selected.append(project.item(item_id).model_dump(mode="json"))
                except KeyError:
                    continue
        except KeyError as error:
            raise HTTPException(404, f"semantic entity not found: {error.args[0]}") from error
        return {
            "project_id": project.id,
            "revision": project.revision,
            "selection": selected,
            "authority": {
                "reversible_commands": sorted(name for name, declaration in COMMAND_REGISTRY.items() if declaration.reversible),
                "context_grants_authority": False,
            },
            "active_commands": [entry.name for entry in _active_commands(project_id)],
            "active_variant": "preview",
            "pending_approvals": [],
        }

    def _active_commands(project_id: str):
        entries = list(COMMAND_REGISTRY.values())
        if store.last_event(project_id) is None:
            entries = [entry for entry in entries if entry.name != "project.undo"]
        return sorted(entries, key=lambda entry: entry.name)

    @application.get("/api/projects/{project_id}/commands/active")
    def get_active_commands(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        project = store.get_project(project_id)
        return {
            "project_id": project.id,
            "revision": project.revision,
            "commands": [entry.model_dump(mode="json") for entry in _active_commands(project_id)],
            "context_grants_authority": False,
        }

    @application.post("/api/projects/{project_id}/assets/uploads", response_model=MediaImportResult)
    def import_asset(
        project_id: str,
        http_request: Request,
        file: UploadFile = File(...),
        request_id: str = Form(..., min_length=8, max_length=120),
        actor: str = Form("browser", min_length=1, max_length=100),
    ) -> MediaImportResult:
        _require_workspace(http_request, project_id)
        try:
            store.get_project(project_id)
        except KeyError as error:
            raise HTTPException(404, "project not found") from error
        effective_actor = getattr(http_request.state, "actor", actor)
        return media.import_file(
            project_id,
            file.file,
            file.filename or "upload",
            file.content_type,
            request_id,
            effective_actor,
        )

    @application.get("/api/projects/{project_id}/assets/{asset_id}")
    def get_asset(project_id: str, asset_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            asset = store.get_project(project_id).asset(asset_id)
        except KeyError as error:
            raise HTTPException(404, "asset not found") from error
        return {"project_id": project_id, "asset": asset.model_dump(mode="json")}

    def _asset_file(project_id: str, asset_id: str, http_request: Request) -> FileResponse:
        _require_workspace(http_request, project_id)
        try:
            project = store.get_project(project_id)
            asset = project.asset(asset_id)
            path = media.path_for_asset(project, asset_id)
        except (KeyError, MediaIntakeError) as error:
            raise HTTPException(404, "managed media not found") from error
        return FileResponse(path, media_type=asset.mime_type, filename=None)

    @application.get("/api/projects/{project_id}/assets/{asset_id}/content")
    def get_asset_content(project_id: str, asset_id: str, http_request: Request) -> FileResponse:
        return _asset_file(project_id, asset_id, http_request)

    @application.get("/api/projects/{project_id}/assets/{asset_id}/proxy")
    def get_asset_proxy(project_id: str, asset_id: str, http_request: Request) -> FileResponse:
        _require_workspace(http_request, project_id)
        try:
            parent = store.get_project(project_id).asset(asset_id)
        except KeyError as error:
            raise HTTPException(404, "asset not found") from error
        if not parent.proxy_asset_id:
            raise HTTPException(404, "asset has no proxy")
        return _asset_file(project_id, parent.proxy_asset_id, http_request)

    @application.get("/api/projects/{project_id}/assets/{asset_id}/thumbnail")
    def get_asset_thumbnail(project_id: str, asset_id: str, http_request: Request) -> FileResponse:
        _require_workspace(http_request, project_id)
        try:
            parent = store.get_project(project_id).asset(asset_id)
        except KeyError as error:
            raise HTTPException(404, "asset not found") from error
        if not parent.thumbnail_asset_id:
            raise HTTPException(404, "asset has no thumbnail")
        return _asset_file(project_id, parent.thumbnail_asset_id, http_request)

    @application.post("/api/projects/{project_id}/selection")
    def set_selection(project_id: str, request: SelectionRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        project = store.get_project(project_id)
        if project.revision != request.expected_revision:
            raise StaleRevisionError(request.expected_revision, project.revision)
        for item_id in request.item_ids:
            try:
                project.item(item_id)
            except KeyError as error:
                raise HTTPException(422, f"unknown item: {item_id}") from error
        store.set_selection(project_id, request.item_ids)
        return {"project_id": project_id, "revision": project.revision, "item_ids": request.item_ids}

    @application.post("/api/projects/{project_id}/commands", response_model=Receipt)
    def execute_command(project_id: str, request: CommandRequest, http_request: Request) -> Receipt:
        _require_workspace(http_request, project_id)
        if hasattr(http_request.state, "actor"):
            request.actor = http_request.state.actor
        try:
            store.get_project(project_id)
        except KeyError as error:
            raise HTTPException(404, "project not found") from error
        return commands.execute(project_id, request)

    @application.post("/api/projects/{project_id}/renders", response_model=Receipt)
    def start_render(project_id: str, request: RenderRequest, http_request: Request) -> Receipt:
        _require_workspace(http_request, project_id)
        duplicate = store.receipt_for_request(project_id, request.request_id)
        if duplicate:
            return duplicate
        project = store.get_project(project_id)
        if project.revision != request.project_revision:
            raise StaleRevisionError(request.project_revision, project.revision)
        spec = renderer.build_spec(project)
        job_id = f"job_{uuid4().hex[:16]}"
        actor = getattr(http_request.state, "actor", request.actor)
        receipt = store.create_receipt(
            project_id=project_id,
            command="render.verified",
            status=ReceiptStatus.ACCEPTED,
            request_id=request.request_id,
            actor=actor,
            project_revision=project.revision,
            payload={"project_revision": project.revision, "job_id": job_id},
        )
        renderer.enqueue(spec, receipt, job_id)
        return receipt

    @application.post("/api/projects/{project_id}/shorts/jobs")
    def start_shorts_job(project_id: str, request: ShortsGenerateRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            job = shorts.enqueue(project_id, request)
        except KeyError as error:
            raise HTTPException(404, "project, revision, or source asset not found") from error
        return asdict(job)

    @application.get("/api/projects/{project_id}/suggestions")
    def list_project_suggestions(
        project_id: str,http_request: Request,state: str | None = None,kind: str | None = None,
        source_revision: int | None = None,job_id: str | None = None,
    ) -> dict:
        _require_workspace(http_request, project_id)
        suggestions = store.list_suggestions(project_id, state=state)
        return {"project_id": project_id, "suggestions": [
            asdict(entry) for entry in suggestions
            if (kind is None or entry.generator_kind == kind)
            and (source_revision is None or entry.source_revision == source_revision)
            and (job_id is None or entry.job_id == job_id)
        ]}

    @application.get("/api/suggestions/{suggestion_id}")
    def get_suggestion(suggestion_id: str, http_request: Request) -> dict:
        try:
            suggestion = store.get_suggestion(suggestion_id)
        except KeyError as error:
            raise HTTPException(404, "suggestion not found") from error
        _require_workspace(http_request, suggestion.project_id)
        return asdict(suggestion)

    @application.post("/api/suggestions/{suggestion_id}/accept")
    def accept_suggestion(suggestion_id: str, request: SuggestionDecisionRequest, http_request: Request) -> dict:
        try:
            suggestion = store.get_suggestion(suggestion_id)
        except KeyError as error:
            raise HTTPException(404, "suggestion not found") from error
        _require_workspace(http_request, suggestion.project_id)
        actor = getattr(http_request.state, "actor", request.actor)
        project, receipt = shorts.accept(suggestion_id, request.request_id, actor, request.name)
        return {"project": project.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")}

    @application.post("/api/suggestions/{suggestion_id}/reject")
    def reject_suggestion(suggestion_id: str, request: SuggestionDecisionRequest, http_request: Request) -> dict:
        try:
            suggestion = store.get_suggestion(suggestion_id)
        except KeyError as error:
            raise HTTPException(404, "suggestion not found") from error
        _require_workspace(http_request, suggestion.project_id)
        return asdict(shorts.reject(suggestion_id))

    @application.get("/api/jobs/{job_id}")
    def get_render_job(job_id: str, http_request: Request) -> dict:
        try:
            job = store.get_job(job_id)
        except KeyError as error:
            raise HTTPException(404, "render job not found") from error
        _require_workspace(http_request, job.project_id)
        return asdict(job)

    @application.post("/api/jobs/{job_id}/cancel")
    def cancel_render_job(job_id: str, http_request: Request) -> dict:
        try:
            job = store.get_job(job_id)
        except KeyError as error:
            raise HTTPException(404, "render job not found") from error
        _require_workspace(http_request, job.project_id)
        if job.state in {"observed_success", "observed_failure", "execution_failed", "cancelled", "timeout", "interrupted"}:
            return asdict(job)
        return asdict(store.request_job_cancellation(job_id))

    @application.get("/api/artifacts/{artifact_id}/content")
    def get_render_artifact(artifact_id: str, http_request: Request) -> FileResponse:
        try:
            artifact = store.get_artifact(artifact_id)
        except KeyError as error:
            raise HTTPException(404, "render artifact not found") from error
        _require_workspace(http_request, artifact.project_id)
        if artifact.managed_uri != f"sag-artifact://{artifact.id}":
            raise HTTPException(404, "invalid render artifact identity")
        path = (artifact_dir / f"{artifact.id}.mp4").resolve()
        if not path.is_relative_to(artifact_dir.resolve()) or not path.is_file():
            raise HTTPException(404, "render artifact bytes not found")
        return FileResponse(path, media_type=artifact.mime_type, filename=None)

    @application.get("/api/projects/{project_id}/receipts", response_model=list[Receipt])
    def list_receipts(project_id: str, http_request: Request) -> list[Receipt]:
        _require_workspace(http_request, project_id)
        return store.list_receipts(project_id)

    @application.get("/api/receipts/{receipt_id}", response_model=Receipt)
    def get_receipt(receipt_id: str, http_request: Request) -> Receipt:
        try:
            receipt = store.get_receipt(receipt_id)
        except KeyError as error:
            raise HTTPException(404, "receipt not found") from error
        _require_workspace(http_request, receipt.project_id)
        return receipt

    @application.post("/api/projects/{project_id}/reset")
    def reset(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        if project_id != "demo":
            raise HTTPException(404, "only the fixture project can be reset")
        project = store.reset_demo()
        return {"project": project.model_dump(mode="json"), "selection": ["title_intro"]}

    @application.post("/api/pairing/start")
    def start_pairing(request: PairStartRequest, http_request: Request) -> dict[str, str]:
        _require_workspace(http_request, request.workspace_id)
        try:
            store.get_project(request.workspace_id)
        except KeyError as error:
            raise HTTPException(404, "workspace not found") from error
        code, expires_at = store.start_pairing(store.workspace_for_project(request.workspace_id))
        return {"code": code, "expires_at": expires_at}

    @application.post("/api/pairing/attach")
    def attach_pairing(request: PairAttachRequest) -> dict[str, str]:
        try:
            token, expires_at, workspace_id = store.attach_pairing(request.code, request.actor_name)
        except ValueError as error:
            raise HTTPException(401, str(error)) from error
        return {"access_token": token, "expires_at": expires_at, "workspace_id": workspace_id}

    @application.get("/api/pairing/status/{workspace_id}")
    def pairing_status(workspace_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, workspace_id)
        try:
            store.get_project(workspace_id)
        except KeyError as error:
            raise HTTPException(404, "workspace not found") from error
        resolved_workspace = store.workspace_for_project(workspace_id)
        actors = store.active_actors(resolved_workspace)
        return {"workspace_id": resolved_workspace, "connected": bool(actors), "actors": actors}

    application.mount("/static", StaticFiles(directory=static_dir), name="static")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    return application


app = create_app()

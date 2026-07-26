from __future__ import annotations

import os
import importlib.util
import hmac
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .commands import CommandService
from .capabilities import detect_capabilities
from .contracts import APPLICATION_ACTIONS, COMMAND_REGISTRY, declared_actions, declared_commands, registry_hash, validate_action_coverage
from .media import MediaIntakeError, MediaService
from .models import (
    CommandBatchRequest,
    CommandProposalRequest,
    ConfirmationCreateRequest,
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
from .blob_storage import FilesystemBlobStorage, GcsBlobStorage
from .repository_factory import create_repository
from .runtime import RuntimeEventService, create_runtime_broker
from .governance import ProtectedProviderConnectionRequest, ProviderConnectionService
from .delivery import (
    DeliveryImportRequest,
    DeliveryProfileRequest,
    DeliveryService,
    ReleaseApprovalRequest,
    ReleaseDispatchRequest,
    delivery_schemas,
)
from .spatial import (
    PROJECTION_VERSION,
    SPATIAL_FRAME_SCHEMA_VERSION,
    SpatialFrameRequest,
    SpatialFrameService,
    SpatialObservationRequest,
    SpatialRegionResolveRequest,
    SpatialDirectiveAck,
    SpatialDirectiveRequest,
    SpatialDirectiveService,
    SpatialProjectionService,
    spatial_schemas,
)
from .semantic_graph import (
    SEMANTIC_PROJECTION_VERSION,
    SemanticGraphAdapter,
    StructuralNeighborhoodRequest,
    semantic_schemas,
)
from .journal import (
    JOURNAL_KIND_DEFINITIONS,
    JOURNAL_PROTOCOL_VERSION,
    InadmissibleJournalPayload,
    JournalEntryRequest,
    SagJournalService,
    journal_schemas,
)
from .x1_context import x1_context_schemas
from .model_registry import MODEL_REGISTRY_VERSION, model_registry, model_registry_hash
from .generative import GenerativeAudioRequest, GenerativeVideoRequest, GoogleGenerativeAdapter, ProviderOperation
from .repo_to_video import (
    CreativeBrief,
    GitHubEvidenceClient,
    RepoStoryboard,
    RepoVideoRequest,
    RepoVideoGenerationRequest,
    SECRET_PATTERNS,
    StoryboardCommitRequest,
    creative_director_prompt,
    evidence_prompt,
    evidence_revision,
    parse_creative_brief,
    prompt_studio_preview,
    prompt_studio_schemas,
    PromptStudioPreviewRequest,
    parse_storyboard,
    proposal_revision,
    resolved_generation_prompt_revision,
    scene_generation_prompt,
    scene_negative_prompt,
    storyboard_response_schema,
)
from .generation_materializer import materialize


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
    repository_backend: str = "sqlite"
    database_url: str = ""
    storage_backend: str = "filesystem"
    storage_root: str = ".sag-video/storage"
    storage_cache_dir: str = ".sag-video/cache"
    gcs_bucket: str = ""
    start_render_worker: bool = True

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
            repository_backend=os.getenv("SAG_REPOSITORY_BACKEND", "sqlite"),
            database_url=os.getenv("DATABASE_URL", ""),
            storage_backend=os.getenv("SAG_STORAGE_BACKEND", "filesystem"),
            storage_root=os.getenv("SAG_VIDEO_STORAGE_ROOT", ".sag-video/storage"),
            storage_cache_dir=os.getenv("SAG_VIDEO_STORAGE_CACHE_DIR", ".sag-video/cache"),
            gcs_bucket=os.getenv("SAG_VIDEO_GCS_BUCKET", ""),
            start_render_worker=os.getenv("SAG_VIDEO_START_RENDER_WORKER", "1").lower() not in {"0", "false", "no"},
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
    store = create_repository(
        backend=settings.repository_backend,
        database_path=settings.database_path,
        database_url=settings.database_url,
    )
    if settings.storage_backend == "filesystem":
        blob_storage = FilesystemBlobStorage(settings.storage_root, settings.storage_cache_dir)
    elif settings.storage_backend == "gcs":
        if not settings.gcs_bucket:
            raise RuntimeError("SAG_VIDEO_GCS_BUCKET is required when SAG_STORAGE_BACKEND=gcs")
        blob_storage = GcsBlobStorage(settings.gcs_bucket, settings.storage_cache_dir)
    else:
        raise RuntimeError(f"unsupported SAG storage backend: {settings.storage_backend}")
    commands = CommandService(store)
    validate_action_coverage(commands.HANDLERS, {
        "shorts_job", "render_job", "shared_focus", "browser_upload", "browser_capture",
        "oauth_connect", "release_approval", "publication_dispatch",
        "focus_entity_directive", "frame_entity_directive", "isolate_neighborhood_directive",
        "reveal_dependencies_directive", "reveal_blast_radius_directive", "set_depth_directive",
        "reset_view_directive",
    })
    runtime = RuntimeEventService(
        store, create_runtime_broker(backend=settings.repository_backend, database_url=settings.database_url)
    )
    spatial = SpatialProjectionService(store)
    spatial_frames = SpatialFrameService(store, spatial, runtime)
    semantic_graph = SemanticGraphAdapter(store, spatial)
    journal = SagJournalService(store, hash_key=os.getenv("SAG_JOURNAL_HMAC_KEY") or None)
    directives = SpatialDirectiveService(store, spatial, runtime, spatial_frames)
    connections = ProviderConnectionService(store)
    delivery = DeliveryService(store, runtime)
    capabilities = detect_capabilities()
    capabilities["generative_media"] = {
        "provider": "google",
        "registry_version": MODEL_REGISTRY_VERSION,
        "registry_hash": model_registry_hash(),
        "models": model_registry(),
        "authentication": {
            "development": "AI Studio API key",
            "production": "Vertex/ADC or protected provider connection",
            "browser_credentials_allowed": False,
        },
    }
    generative = GoogleGenerativeAdapter()
    repo_evidence = GitHubEvidenceClient(os.getenv("GITHUB_TOKEN") or None)
    media = MediaService(
        store,
        settings.media_dir,
        settings.proxy_dir,
        upload_limit_bytes=settings.upload_limit_bytes,
        blob_storage=blob_storage,
    )
    renderer = RenderService(
        store,
        artifact_dir,
        media.path_for_asset,
        observer=_remote_observer(settings.observer_url) if settings.observer_url else __import__(
            "sag_video.observer", fromlist=["observe_artifact"]
        ).observe_artifact,
        blob_storage=blob_storage,
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
        if settings.start_render_worker:
            worker.start()
        if settings.start_analysis_worker:
            analysis_worker.start()
        try:
            yield
        finally:
            if settings.start_render_worker:
                worker.stop()
            analysis_worker.stop()
            runtime.broker.close()
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
    application.state.runtime = runtime
    application.state.spatial = spatial
    application.state.semantic_graph = semantic_graph
    application.state.journal = journal
    application.state.directives = directives
    application.state.connections = connections
    application.state.delivery = delivery
    application.state.generative = generative
    application.state.repo_evidence = repo_evidence
    application.state.spatial_frames = spatial_frames

    def _require_workspace(request: Request, project_id: str) -> None:
        workspace_id = getattr(request.state, "workspace_id", None)
        if workspace_id not in {None, "*"} and not store.project_in_workspace(project_id, workspace_id):
            raise HTTPException(403, "paired token is scoped to another workspace")
        scoped_project = getattr(request.state, "project_id", None)
        if scoped_project and scoped_project != project_id:
            raise HTTPException(403, "paired token is scoped to another project")

    def _require_workspace_identity(request: Request, workspace_id: str) -> None:
        scoped_workspace = getattr(request.state, "workspace_id", None)
        if scoped_workspace not in {None, "*", workspace_id}:
            raise HTTPException(403, "paired token is scoped to another workspace")

    def _scopes(request: Request) -> list[str]:
        return list(getattr(request.state, "scopes", ["*"]))

    def _require_scope(request: Request, scope: str) -> None:
        scopes = _scopes(request)
        if "*" not in scopes and scope not in scopes:
            raise HTTPException(403, f"missing required scope: {scope}")

    def _emit_receipt_transition(receipt: Any) -> None:
        project = store.get_project(receipt.project_id)
        runtime.emit(
            workspace_id=str(project.workspace_id or project.id), project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=receipt.actor, kind="receipt.transitioned",
            payload={"receipt_id": receipt.id, "status": str(receipt.status)},
        )

    @application.get("/api/workspaces/{workspace_id}/connections")
    def list_provider_connections(workspace_id: str, http_request: Request) -> dict:
        _require_workspace_identity(http_request, workspace_id)
        _require_scope(http_request, "connections:admin")
        return {"connections": [entry.model_dump(mode="json") for entry in connections.list(workspace_id)]}

    @application.post("/api/workspaces/{workspace_id}/connections", status_code=201)
    def put_provider_connection(
        workspace_id: str, body: ProtectedProviderConnectionRequest, http_request: Request,
    ) -> dict:
        _require_workspace_identity(http_request, workspace_id)
        _require_scope(http_request, "connections:admin")
        return connections.put(workspace_id, body).model_dump(mode="json")

    @application.get("/api/workspaces/{workspace_id}/connections/{connection_id}/protected")
    def get_protected_provider_connection(
        workspace_id: str, connection_id: str, http_request: Request,
    ) -> dict:
        _require_workspace_identity(http_request, workspace_id)
        if not getattr(http_request.state, "service_authenticated", False):
            raise HTTPException(403, "protected connection material is service-only")
        _require_scope(http_request, "connections:secret")
        try:
            return connections.protected(workspace_id, connection_id)
        except KeyError as error:
            raise HTTPException(404, "provider connection not found") from error

    @application.delete("/api/workspaces/{workspace_id}/connections/{connection_id}")
    def revoke_provider_connection(
        workspace_id: str, connection_id: str, http_request: Request,
    ) -> dict:
        _require_workspace_identity(http_request, workspace_id)
        _require_scope(http_request, "connections:admin")
        try:
            return connections.revoke(workspace_id, connection_id).model_dump(mode="json")
        except KeyError as error:
            raise HTTPException(404, "provider connection not found") from error

    @application.get("/api/projects/{project_id}/delivery")
    def get_delivery_state(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        return delivery.state(project_id)

    @application.post("/api/projects/{project_id}/delivery/profiles", status_code=201)
    def put_delivery_profile(
        project_id: str, body: DeliveryProfileRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "release:prepare")
        return delivery.put_profile(project_id, body)

    @application.post("/api/projects/{project_id}/delivery/import")
    def import_delivery_state(
        project_id: str, body: DeliveryImportRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        if not getattr(http_request.state, "service_authenticated", False):
            raise HTTPException(403, "delivery migration is service-only")
        _require_scope(http_request, "release:migrate")
        return delivery.import_legacy(project_id, body)

    @application.post("/api/projects/{project_id}/release/approvals", status_code=201)
    def create_release_approval(
        project_id: str, body: ReleaseApprovalRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "release:approve")
        try:
            approval, receipt = delivery.approve(project_id, body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"approval": approval, "receipt": receipt.model_dump(mode="json")}

    @application.post("/api/projects/{project_id}/release/approvals/{approval_id}/dispatch", status_code=202)
    def dispatch_release_approval(
        project_id: str, approval_id: str, body: ReleaseDispatchRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "release:prepare")
        try:
            approval, attempts, receipt = delivery.dispatch(
                project_id, approval_id, body, actor=getattr(http_request.state, "actor", "browser"),
            )
        except KeyError as error:
            raise HTTPException(404, "release approval not found") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"approval": approval, "attempts": attempts, "receipt": receipt.model_dump(mode="json")}

    def _require_unscoped(request: Request) -> None:
        if getattr(request.state, "service_authenticated", False):
            return
        workspace_id = getattr(request.state, "workspace_id", None)
        if workspace_id not in {None, "*"}:
            raise HTTPException(403, "paired project token cannot create projects")

    @application.middleware("http")
    async def invite_gate(request: Request, call_next):
        service_header = request.headers.get("x-sag-service-token", "")
        cloud_run_iam = (
            os.getenv("SAG_TRUST_CLOUD_RUN_IAM", "0").lower() in {"1", "true", "yes"}
            and request.headers.get("authorization", "").startswith("Bearer ")
        )
        if (settings.service_token and hmac.compare_digest(service_header, settings.service_token)) or cloud_run_iam:
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
            request.state.project_id = principal.get("project_id")
            request.state.sequence_id = principal.get("sequence_id")
            request.state.scopes = principal.get("scopes", [])
            request.state.pairing_token = principal.get("token")
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
            session_token, _ = store.issue_token("*", "browser", scopes=["*"])
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
            "application": {"id": "sag-video", "name": "SAG Video", "contract_version": "0.2", "protocol_versions": ["sag-http-0.2"]},
            "registry_hash": registry_hash(),
            "entities": {
                "workspace": {"identity": "stable workspace.id containing source and derived projects"},
                "project": {"identity": "stable project.id"},
                "asset": {"identity": "stable asset.id scoped to a project"},
                "timeline_item": {"identity": "stable timeline item.id scoped to a project"},
                "receipt": {"identity": "stable causal receipt.id"},
                "job": {"identity": "stable persistent job.id"},
                "artifact": {"identity": "stable observed artifact.id scoped to a project"},
                "delivery_profile": {"identity": "stable engine-owned delivery profile.id scoped to a project"},
                "release_approval": {"identity": "stable engine-owned approval.id bound to revision, artifact hashes, destinations, and human actor"},
                "publication_attempt": {"identity": "stable engine-owned attempt.id bound to one approval and destination"},
                "analysis_artifact": {"identity": "immutable provider-and-settings-versioned analysis.id"},
                "suggestion": {"identity": "stable auditable suggestion.id tied to an exact source revision"},
            },
            "commands": declared_commands(),
            "actions": declared_actions(),
            "event_definitions": runtime.definitions(),
            "spatial_schemas": spatial_schemas(),
            "semantic_graph_schemas": semantic_schemas(),
            "x1_context_schemas": x1_context_schemas(),
            "semantic_projection_version": SEMANTIC_PROJECTION_VERSION,
            "journal_protocol_version": JOURNAL_PROTOCOL_VERSION,
            "journal_schemas": journal_schemas(),
            "journal_kinds": list(JOURNAL_KIND_DEFINITIONS),
            "delivery_schemas": delivery_schemas(),
            "generative_media": capabilities["generative_media"],
            "prompt_studio_schema_version": "sag-prompt-studio/0.1",
            "prompt_studio_schemas": prompt_studio_schemas(),
            "projection_version": PROJECTION_VERSION,
            "spatial_frame_schema_version": SPATIAL_FRAME_SCHEMA_VERSION,
            "spatial_computer_use": {
                "frame_declarations": True,
                "semantic_actuation": True,
                "gemini_observer": os.getenv("SAG_GEMINI_OBSERVER_ENABLED", "").lower() in {"1", "true", "yes"},
                "coordinate_fallback": os.getenv("SAG_COORDINATE_FALLBACK_ENABLED", "").lower() in {"1", "true", "yes"},
                "raw_frame_retention": False,
            },
            "spatial_actions": [
                action for action in declared_actions() if action["name"].startswith("spatial.")
            ],
            "authority": {
                "actor": actor,
                "scopes": _scopes(http_request),
                "project_id": getattr(http_request.state, "project_id", None),
                "sequence_id": getattr(http_request.state, "sequence_id", None),
                "declared_required_scopes": sorted({entry.required_scope for entry in COMMAND_REGISTRY.values()}),
                "context_grants_authority": False,
                "note": "The server evaluates actual authentication, revision, target, and arguments on every invocation.",
            },
            "receipts": {
                "dispatch_is_success": False,
                "terminal_states": ["committed", "observed_success", "observed_failure", "execution_failed", "denied", "cancelled", "timeout"],
                "render_nonterminal_states": ["accepted", "dispatched", "rendering", "artifact_written", "awaiting_observation"],
            },
            "capabilities": capabilities,
        }

    @application.post("/api/projects/{project_id}/generative/video", status_code=202)
    def start_generative_video(project_id: str, body: GenerativeVideoRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:write")
        project = store.get_project(project_id)
        try:
            operation = generative.start_video(body)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        receipt = store.create_receipt(
            project_id=project_id, command="media.generate_video", status=ReceiptStatus.ACCEPTED,
            request_id=operation.request_id, actor=getattr(http_request.state, "actor", "browser"),
            project_revision=project.revision,
            payload={"provider": operation.provider, "model": operation.model, "operation_name": operation.operation_name,
                     "request_hash": operation.request_id.removeprefix("gen_")},
        )
        return {"operation": operation.model_copy(update={"request_id": receipt.id}).model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")}

    @application.post("/api/projects/{project_id}/generative/audio", status_code=202)
    def start_generative_audio(project_id: str, body: GenerativeAudioRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:write")
        project = store.get_project(project_id)
        try:
            operation = generative.start_audio(body)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(422, str(error)) from error
        receipt = store.create_receipt(
            project_id=project_id, command="media.generate_audio", status=ReceiptStatus.ACCEPTED,
            request_id=operation.request_id, actor=getattr(http_request.state, "actor", "browser"),
            project_revision=project.revision,
            payload={"provider": operation.provider, "model": operation.model, "operation_name": operation.operation_name,
                     "request_hash": operation.request_id.removeprefix("gen_")},
        )
        return {"operation": operation.model_copy(update={"request_id": receipt.id}).model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")}

    @application.get("/api/projects/{project_id}/generative/receipts/{receipt_id}")
    def poll_generative(project_id: str, receipt_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            receipt = store.get_receipt(receipt_id)
        except KeyError as error:
            raise HTTPException(404, "generative receipt not found") from error
        if receipt.project_id != project_id:
            raise HTTPException(404, "generative receipt not found")
        operation_name = receipt.payload.get("operation_name")
        if not operation_name:
            raise HTTPException(409, "receipt has no provider operation")
        operation = ProviderOperation(request_id=receipt.id, model=str(receipt.payload.get("model")), operation_name=str(operation_name))
        try:
            observed = generative.poll(operation)
        except RuntimeError as error:
            receipt = store.update_receipt(receipt, ReceiptStatus.EXECUTION_FAILED, {"error_code": "provider_poll_failed", "error_detail": str(error)})
            raise HTTPException(502, str(error)) from error
        if observed.state == "completed":
            receipt = store.update_receipt(receipt, ReceiptStatus.AWAITING_OBSERVATION, {"provider_output": {"available": True}})
        elif observed.state == "failed":
            receipt = store.update_receipt(receipt, ReceiptStatus.EXECUTION_FAILED, {"error_code": observed.error_code, "error_detail": observed.error_detail})
        return {"operation": observed.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")}

    @application.post("/api/projects/{project_id}/repo-to-video/evidence")
    def inspect_repository_for_video(project_id: str, body: RepoVideoRequest, http_request: Request) -> dict:
        """Fetch bounded repository evidence for a later human-approved storyboard."""
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:read")
        try:
            evidence = repo_evidence.fetch(body)
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(422, f"repository evidence unavailable: {error}") from error
        return {
            "evidence": evidence.model_dump(mode="json"),
            "evidence_revision": evidence_revision(evidence),
            "redaction": {"status": "passed", "bounded": True, "secret_patterns_applied": len(SECRET_PATTERNS)},
            "factuality": {"status": "evidence_bound", "unsupported_claims_allowed": False},
            "next_step": "generate_creative_brief_then_review_storyboard",
        }

    @application.post("/api/projects/{project_id}/repo-to-video/storyboard", status_code=202)
    def propose_repository_storyboard(project_id: str, body: RepoVideoRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:write")
        try:
            evidence = repo_evidence.fetch(body)
            raw = generative.plan_text(
                model="gemini-omni-flash-preview",
                prompt=evidence_prompt(body, evidence),
                response_schema=storyboard_response_schema(evidence),
            )
            storyboard = parse_storyboard(raw, evidence=evidence, requested_duration_seconds=body.duration_seconds)
        except (httpx.HTTPError, RuntimeError, ValueError) as error:
            raise HTTPException(422, f"storyboard proposal rejected: {error}") from error
        project = store.get_project(project_id)
        request_id = f"storyboard_{evidence_revision(evidence)[:12]}_{proposal_revision(storyboard)[:12]}"
        receipt = store.create_receipt(
            project_id=project_id, command="media.propose_storyboard", status=ReceiptStatus.AWAITING_USER_CONSENT,
            request_id=request_id, actor=getattr(http_request.state, "actor", "browser"), project_revision=project.revision,
            payload={"provider": "google", "model": "gemini-omni-flash-preview", "evidence_revision": storyboard.evidence_revision,
                     "scene_count": len(storyboard.scenes), "duration_seconds": sum(scene.duration_seconds for scene in storyboard.scenes),
                     "requested_duration_seconds": body.duration_seconds,
                     "allowed_evidence_refs": sorted({"README.md", *evidence.files, *evidence.manifests.keys()}),
                     "repository": {"url": evidence.repository_url, "ref": evidence.ref, "name": evidence.name},
                     "storyboard": storyboard.model_dump(mode="json")},
        )
        _emit_receipt_transition(receipt)
        return {"storyboard": storyboard.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")}

    @application.post("/api/projects/{project_id}/repo-to-video/director/brief", status_code=202)
    def propose_creative_brief(project_id: str, body: RepoVideoRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:write")
        try:
            evidence = repo_evidence.fetch(body)
            raw = generative.plan_text(
                model="gemini-omni-flash-preview",
                prompt=creative_director_prompt(body, evidence),
                response_schema=CreativeBrief.model_json_schema(),
            )
            brief = parse_creative_brief(raw, evidence=evidence)
        except (httpx.HTTPError, RuntimeError, ValueError) as error:
            raise HTTPException(422, f"creative brief rejected: {error}") from error
        project = store.get_project(project_id)
        receipt = store.create_receipt(
            project_id=project_id, command="media.propose_creative_brief", status=ReceiptStatus.AWAITING_USER_CONSENT,
            request_id=f"brief_{evidence_revision(evidence)[:12]}_{proposal_revision(brief)[:12]}", actor=getattr(http_request.state, "actor", "browser"),
            project_revision=project.revision,
            payload={"provider": "google", "model": "gemini-omni-flash-preview", "evidence_revision": brief.evidence_revision,
                     "narrative_beats": len(brief.narrative_arc),
                     "repository": {"url": evidence.repository_url, "ref": evidence.ref, "name": evidence.name},
                     "creative_brief": brief.model_dump(mode="json")},
        )
        _emit_receipt_transition(receipt)
        return {"brief": brief.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json"), "next_step": "review_brief_then_generate_storyboard"}

    @application.post("/api/projects/{project_id}/repo-to-video/prompts/preview")
    def preview_repository_video_prompts(project_id: str, body: PromptStudioPreviewRequest, http_request: Request) -> dict:
        """Compile the exact provider-facing prompt bundle without dispatching media generation."""
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:read")
        store.get_project(project_id)
        return {
            **prompt_studio_preview(body),
            "model_registry_version": MODEL_REGISTRY_VERSION,
            "model_registry_hash": model_registry_hash(),
            "models": model_registry(),
        }

    @application.post("/api/projects/{project_id}/repo-to-video/storyboard/commit")
    def commit_repository_storyboard(project_id: str, body: StoryboardCommitRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:write")
        human_confirmation = http_request.headers.get("x-sag-human-confirmation", "")
        human_confirmed_proxy = (
            getattr(http_request.state, "service_authenticated", False)
            and hmac.compare_digest(human_confirmation, body.confirmation_id)
        )
        if getattr(http_request.state, "actor", "") != "browser" and not human_confirmed_proxy:
            raise HTTPException(403, "human browser confirmation is required")
        try:
            receipt = store.get_receipt(body.receipt_id)
        except KeyError as error:
            raise HTTPException(404, "storyboard receipt not found") from error
        if receipt.project_id != project_id or receipt.command != "media.propose_storyboard":
            raise HTTPException(404, "storyboard receipt not found")
        project = store.get_project(project_id)
        if project.revision != body.expected_revision or receipt.project_revision != body.expected_revision:
            raise StaleRevisionError(body.expected_revision, project.revision)
        if receipt.status != ReceiptStatus.AWAITING_USER_CONSENT:
            return {"receipt": receipt.model_dump(mode="json"), "idempotent": True}
        reviewed_storyboard = body.storyboard
        if reviewed_storyboard is not None:
            if reviewed_storyboard.evidence_revision != receipt.payload.get("evidence_revision"):
                raise HTTPException(409, "reviewed storyboard evidence revision differs from the proposal")
            requested_duration = float(receipt.payload.get("requested_duration_seconds") or 0)
            reviewed_end = max(
                (scene.start_seconds + scene.duration_seconds for scene in reviewed_storyboard.scenes), default=0,
            )
            if requested_duration and reviewed_end > requested_duration + 0.01:
                raise HTTPException(409, "reviewed storyboard exceeds the proposed production duration")
            allowed_refs = set(receipt.payload.get("allowed_evidence_refs") or [])
            if allowed_refs:
                invalid_refs = sorted({
                    reference
                    for scene in reviewed_storyboard.scenes
                    for reference in scene.evidence_refs
                    if reference.split("#", 1)[0].split(":", 1)[0].strip() not in allowed_refs
                })
                if invalid_refs:
                    raise HTTPException(409, "reviewed storyboard contains evidence references outside the proposal")
        approved_storyboard = reviewed_storyboard.model_dump(mode="json") if reviewed_storyboard is not None else receipt.payload.get("storyboard")
        updated = store.update_receipt(receipt, ReceiptStatus.COMMITTED, {
            "human_confirmation_id": body.confirmation_id,
            "approved_by": getattr(http_request.state, "actor", "browser"),
            "storyboard": approved_storyboard,
            "approved_storyboard_revision": proposal_revision(reviewed_storyboard) if reviewed_storyboard is not None else None,
        })
        _emit_receipt_transition(updated)
        return {"receipt": updated.model_dump(mode="json"), "next_step": "enqueue_scene_generation_and_observation"}

    @application.post("/api/projects/{project_id}/repo-to-video/generate", status_code=202)
    def generate_repository_video(project_id: str, body: RepoVideoGenerationRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:write")
        human_confirmation = http_request.headers.get("x-sag-human-confirmation", "")
        human_confirmed_proxy = (
            getattr(http_request.state, "service_authenticated", False)
            and hmac.compare_digest(human_confirmation, body.confirmation_id)
        )
        if getattr(http_request.state, "actor", "") != "browser" and not human_confirmed_proxy:
            raise HTTPException(403, "human browser confirmation is required")
        project = store.get_project(project_id)
        if project.revision != body.expected_revision:
            raise StaleRevisionError(body.expected_revision, project.revision)
        try:
            approval_receipt = store.get_receipt(body.storyboard_receipt_id)
        except KeyError as error:
            raise HTTPException(404, "approved storyboard receipt not found") from error
        if approval_receipt.project_id != project_id or approval_receipt.command != "media.propose_storyboard":
            raise HTTPException(404, "approved storyboard receipt not found")
        if approval_receipt.status != ReceiptStatus.COMMITTED:
            raise HTTPException(409, "storyboard receipt is not human-approved")
        approved_payload = approval_receipt.payload.get("storyboard")
        if not isinstance(approved_payload, dict):
            raise HTTPException(409, "approved storyboard receipt has no bound storyboard")
        try:
            approved_storyboard = RepoStoryboard.model_validate(approved_payload)
        except ValueError as error:
            raise HTTPException(409, "approved storyboard receipt is malformed") from error
        if proposal_revision(approved_storyboard) != proposal_revision(body.storyboard):
            raise HTTPException(409, "requested storyboard differs from the human-approved proposal")
        if body.storyboard.evidence_revision != body.creative_brief.evidence_revision:
            raise HTTPException(409, "creative brief and storyboard evidence revisions differ")
        storyboard_revision = proposal_revision(body.storyboard)
        brief_revision = proposal_revision(body.creative_brief)
        prompt_revision = resolved_generation_prompt_revision(
            body.storyboard, body.creative_brief, aspect_ratio=body.aspect_ratio,
        )
        attempt_revision = hashlib.sha256(body.idempotency_key.encode()).hexdigest()[:10]
        request_id = (
            f"repo_video_{storyboard_revision[:12]}_{prompt_revision[:12]}_"
            f"{body.aspect_ratio.replace(':', '_')}_{attempt_revision}"
        )
        existing = store.receipt_for_request(project_id, request_id)
        if existing is not None:
            existing_operations = [
                {
                    "request_id": existing.id,
                    "provider": "google",
                    "state": "pending",
                    **item,
                }
                for item in existing.payload.get("operations", [])
            ]
            return {"receipt": existing.model_dump(mode="json"), "operations": existing_operations, "idempotent": True}

        receipt = store.create_receipt(
            project_id=project_id, command="media.repo_to_video_generation", status=ReceiptStatus.ACCEPTED,
            request_id=request_id, actor=getattr(http_request.state, "actor", "browser"), project_revision=project.revision,
            payload={
                "confirmation_id": body.confirmation_id,
                "evidence_revision": body.storyboard.evidence_revision,
                "storyboard_revision": storyboard_revision,
                "creative_brief_revision": brief_revision,
                "resolved_prompt_revision": prompt_revision,
                "idempotency_key_hash": attempt_revision,
                "aspect_ratio": body.aspect_ratio,
                "dispatch_state": "running",
                "operations": [],
            },
        )
        _emit_receipt_transition(receipt)
        operations: list[dict[str, Any]] = []

        def _stored_operations() -> list[dict[str, Any]]:
            return [
                {
                    "kind": item["kind"],
                    "scene_id": item.get("scene_id"),
                    "operation_name": item["operation_name"],
                    "model": item["model"],
                    "state": item.get("state", "pending"),
                    **({"asset_id": item["asset_id"]} if item.get("asset_id") else {}),
                }
                for item in operations
            ]

        def _register_started(kind: str, operation: ProviderOperation, scene_id: str | None = None) -> None:
            nonlocal receipt
            item: dict[str, Any] = {
                "kind": kind,
                "scene_id": scene_id,
                "request_id": operation.request_id,
                "provider": operation.provider,
                "model": operation.model,
                "operation_name": operation.operation_name,
                "state": operation.state,
            }
            operations.append(item)
            receipt = store.update_receipt(receipt, ReceiptStatus.ACCEPTED, {"operations": _stored_operations()})
            if operation.state == "failed":
                raise RuntimeError(operation.error_detail or "provider operation failed during dispatch")
            if operation.state != "completed":
                return
            if not operation.output:
                raise ValueError("provider completed during dispatch without materializable media")
            imported = materialize(
                media, project_id, operation.output,
                request_id=f"{receipt.id}_{kind}_{scene_id or 'all'}",
                actor=getattr(http_request.state, "actor", "browser"),
            )
            if imported.asset is None or imported.receipt.status != ReceiptStatus.OBSERVED_SUCCESS:
                raise ValueError("provider media failed canonical observation during dispatch")
            item["asset_id"] = imported.asset.id
            current = store.get_project(project_id)
            insert_receipt = commands.execute(
                project_id,
                CommandRequest(
                    command="timeline.insert_asset", arguments={"asset_id": imported.asset.id},
                    expected_revision=current.revision, request_id=f"{receipt.id}_insert_{imported.asset.id}",
                    actor=getattr(http_request.state, "actor", "browser"),
                ),
                scopes=_scopes(http_request),
            )
            if insert_receipt.status != ReceiptStatus.COMMITTED:
                raise ValueError("observed provider asset could not be inserted on the canonical timeline")
            receipt = store.update_receipt(receipt, ReceiptStatus.ACCEPTED, {"operations": _stored_operations()})

        try:
            for scene in body.storyboard.scenes:
                model = scene.generation_model if scene.generation_model in {"gemini-omni-flash-preview", "veo-3.1-generate-preview", "veo-3.1-lite-generate-preview"} else "gemini-omni-flash-preview"
                prompt = scene_generation_prompt(scene, body.creative_brief, aspect_ratio=body.aspect_ratio)
                operation = generative.start_video(GenerativeVideoRequest(
                    model=model,
                    prompt=prompt,
                    duration_seconds=min(scene.duration_seconds, 30),
                    aspect_ratio=body.aspect_ratio,
                    negative_prompt="" if model == "gemini-omni-flash-preview" else scene_negative_prompt(aspect_ratio=body.aspect_ratio),
                ))
                _register_started("video", operation, scene.id)
            music = generative.start_audio(GenerativeAudioRequest(model="lyria-3-clip-preview", text=body.creative_brief.music_prompt, duration_seconds=min(sum(scene.duration_seconds for scene in body.storyboard.scenes), 30)))
            _register_started("music", music)
            narration = generative.start_audio(GenerativeAudioRequest(model="gemini-3.1-flash-tts-preview", text=" ".join(scene.narration for scene in body.storyboard.scenes), duration_seconds=min(sum(scene.duration_seconds for scene in body.storyboard.scenes), 600)))
            _register_started("narration", narration)
            final_status = (
                ReceiptStatus.OBSERVED_SUCCESS
                if operations and all(item.get("asset_id") for item in operations)
                else ReceiptStatus.ACCEPTED
            )
            receipt = store.update_receipt(receipt, final_status, {
                "dispatch_state": "completed",
                "operations": _stored_operations(),
            })
            if final_status == ReceiptStatus.OBSERVED_SUCCESS:
                _emit_receipt_transition(receipt)
        except (OSError, RuntimeError, ValueError, httpx.HTTPError) as error:
            detail = str(error)
            receipt = store.update_receipt(receipt, ReceiptStatus.EXECUTION_FAILED, {
                "dispatch_state": "failed",
                "dispatch_error_code": "quota_failure" if detail.startswith("quota_failure:") else "provider_dispatch_failed",
                "dispatch_error_detail": detail[:500],
                "operations": _stored_operations(),
            })
            _emit_receipt_transition(receipt)
            return {"receipt": receipt.model_dump(mode="json"), "operations": operations, "partial": bool(operations)}
        return {"receipt": receipt.model_dump(mode="json"), "operations": operations}

    @application.get("/api/projects/{project_id}/repo-to-video/generation/{receipt_id}")
    def poll_repository_video(project_id: str, receipt_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            receipt = store.get_receipt(receipt_id)
        except KeyError as error:
            raise HTTPException(404, "repo-to-video generation receipt not found") from error
        if receipt.project_id != project_id or receipt.command != "media.repo_to_video_generation":
            raise HTTPException(404, "repo-to-video generation receipt not found")
        initial_status = receipt.status
        results: list[dict[str, Any]] = []
        failed = receipt.payload.get("dispatch_state") == "failed"
        all_done = True
        for item in receipt.payload.get("operations", []):
            asset_id = item.get("asset_id")
            operation = ProviderOperation(
                request_id=receipt.id, model=str(item["model"]), operation_name=str(item["operation_name"]),
                state="completed" if asset_id else "pending",
            )
            if asset_id:
                results.append({"kind": item["kind"], "scene_id": item.get("scene_id"), "asset_id": asset_id, **operation.model_dump(mode="json")})
                continue
            try:
                observed = generative.poll(operation)
            except RuntimeError as error:
                observed = operation.model_copy(update={"state": "failed", "error_code": "provider_poll_failed", "error_detail": str(error)})
            failed = failed or observed.state == "failed"
            all_done = all_done and observed.state in {"completed", "failed"}
            if observed.state == "completed" and not asset_id:
                if not observed.output:
                    failed = True
                    observed = observed.model_copy(update={"state": "failed", "error_code": "provider_output_missing", "error_detail": "provider completed without downloadable media"})
                else:
                    try:
                        imported = materialize(media, project_id, observed.output, request_id=f"{receipt.id}_{item['kind']}_{item.get('scene_id', 'all')}", actor=getattr(http_request.state, "actor", "browser"))
                        if imported.asset is None or imported.receipt.status != ReceiptStatus.OBSERVED_SUCCESS:
                            raise ValueError("downloaded provider media failed canonical observation")
                        asset_id = imported.asset.id
                        item["asset_id"] = asset_id
                        current = store.get_project(project_id)
                        insert_receipt = commands.execute(project_id, CommandRequest(command="timeline.insert_asset", arguments={"asset_id": asset_id}, expected_revision=current.revision, request_id=f"{receipt.id}_insert_{asset_id}", actor=getattr(http_request.state, "actor", "browser")), scopes=_scopes(http_request))
                        if insert_receipt.status != ReceiptStatus.COMMITTED:
                            raise ValueError("observed provider asset could not be inserted on the canonical timeline")
                    except (OSError, ValueError, httpx.HTTPError) as error:
                        failed = True
                        observed = observed.model_copy(update={"state": "failed", "error_code": "media_materialization_failed", "error_detail": str(error)})
            results.append({"kind": item["kind"], "scene_id": item.get("scene_id"), "asset_id": asset_id, **observed.model_dump(mode="json")})
        if not failed and any(item.get("asset_id") for item in receipt.payload.get("operations", [])) and not all_done:
            receipt = store.update_receipt(receipt, receipt.status, {"operations": receipt.payload.get("operations", [])})
        if failed:
            receipt = store.update_receipt(receipt, ReceiptStatus.EXECUTION_FAILED, {"operations_completed": all_done, "assets": [{"kind": item["kind"], "scene_id": item.get("scene_id"), "asset_id": item.get("asset_id")} for item in receipt.payload.get("operations", []) if item.get("asset_id")]})
        elif all_done:
            receipt = store.update_receipt(receipt, ReceiptStatus.OBSERVED_SUCCESS, {"operations_completed": True, "assets": [{"kind": item["kind"], "scene_id": item.get("scene_id"), "asset_id": item.get("asset_id")} for item in receipt.payload.get("operations", []) if item.get("asset_id")]})
        if receipt.status != initial_status:
            _emit_receipt_transition(receipt)
        return {"receipt": receipt.model_dump(mode="json"), "operations": results}

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
        token = getattr(http_request.state, "pairing_token", None)
        actor_focus = store.get_actor_focus(token, project_id)
        active = _command_projection(project_id, http_request)
        return {
            "project_id": project.id,
            "sequence_id": getattr(http_request.state, "sequence_id", None) or project.id,
            "revision": project.revision,
            "shared_focus": selected,
            "selection": selected,
            "actor_focus": actor_focus,
            "authority": {
                "actor": getattr(http_request.state, "actor", "browser"),
                "scopes": _scopes(http_request),
                "project_boundary": getattr(http_request.state, "project_id", None),
                "context_grants_authority": False,
            },
            "active_commands": [entry["name"] for entry in active if entry["eligible"]],
            "command_eligibility": active,
            "action_eligibility": _action_projection(project_id, http_request),
            "visible_surface": actor_focus["visible_surface"],
            "active_workflow": actor_focus["active_workflow"],
            "pending_approvals": [],
        }

    def _active_commands(project_id: str):
        entries = list(COMMAND_REGISTRY.values())
        if store.previous_edit_revision(project_id) is None:
            entries = [entry for entry in entries if entry.name != "project.undo"]
        if store.next_edit_revision(project_id) is None:
            entries = [entry for entry in entries if entry.name != "project.redo"]
        return sorted(entries, key=lambda entry: entry.name)

    def _command_projection(project_id: str, request: Request) -> list[dict]:
        scopes = _scopes(request)
        projected = []
        for entry in _active_commands(project_id):
            eligible = "*" in scopes or entry.required_scope in scopes
            reason = None if eligible else f"missing required scope: {entry.required_scope}"
            projected.append({
                "name": entry.name, "eligible": eligible, "reason": reason,
                "safety_class": entry.safety_class,
                "confirmation_policy": entry.confirmation_policy,
                "required_scope": entry.required_scope,
            })
        return projected

    def _action_projection(project_id: str, request: Request) -> list[dict]:
        scopes = _scopes(request)
        combined = {**COMMAND_REGISTRY, **APPLICATION_ACTIONS}
        entries = [
            entry for entry in combined.values()
            if (entry.name != "project.undo" or store.previous_edit_revision(project_id) is not None)
            and (entry.name != "project.redo" or store.next_edit_revision(project_id) is not None)
        ]
        projected = []
        for entry in sorted(entries, key=lambda value: value.name):
            eligible = ("*" in scopes or entry.required_scope in scopes) and "mcp" in entry.eligible_surfaces
            reason = None
            if "mcp" not in entry.eligible_surfaces:
                reason = entry.ineligible_reason or "action is not eligible from this surface"
            elif "*" not in scopes and entry.required_scope not in scopes:
                reason = f"missing required scope: {entry.required_scope}"
            projected.append({
                "name": entry.name, "eligible": eligible, "reason": reason,
                "safety_class": entry.safety_class, "confirmation_policy": entry.confirmation_policy,
                "required_scope": entry.required_scope, "source_hash": entry.source_hash,
            })
        return projected

    @application.get("/api/projects/{project_id}/commands/active")
    def get_active_commands(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        project = store.get_project(project_id)
        return {
            "project_id": project.id,
            "revision": project.revision,
            "commands": [entry.model_dump(mode="json") for entry in _active_commands(project_id)],
            "eligibility": _command_projection(project_id, http_request),
            "actions": declared_actions(),
            "action_eligibility": _action_projection(project_id, http_request),
            "registry_hash": registry_hash(),
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
        token = getattr(http_request.state, "pairing_token", None)
        if token:
            _require_scope(http_request, "focus:write")
            store.set_actor_focus(token, project_id, request.item_ids)
            runtime.emit(
                workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
                revision=project.revision, actor=getattr(http_request.state, "actor", request.actor),
                kind="actor.focus_changed", payload={"entity_ids": request.item_ids, "focus": "actor_local"},
            )
            return {"project_id": project_id, "revision": project.revision, "item_ids": request.item_ids, "focus": "actor_local"}
        store.set_selection(project_id, request.item_ids)
        runtime.emit(
            workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=getattr(http_request.state, "actor", request.actor),
            kind="studio.focus_changed", payload={"entity_ids": request.item_ids, "focus": "shared"},
        )
        return {"project_id": project_id, "revision": project.revision, "item_ids": request.item_ids, "focus": "shared"}

    @application.post("/api/projects/{project_id}/focus/shared")
    def set_shared_focus(project_id: str, request: SelectionRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "focus:write")
        project = store.get_project(project_id)
        if project.revision != request.expected_revision:
            raise StaleRevisionError(request.expected_revision, project.revision)
        for item_id in request.item_ids:
            try:
                project.item(item_id)
            except KeyError as error:
                raise HTTPException(422, f"unknown item: {item_id}") from error
        store.set_selection(project_id, request.item_ids)
        return {"project_id": project_id, "revision": project.revision, "item_ids": request.item_ids, "focus": "shared"}

    @application.post("/api/projects/{project_id}/commands", response_model=Receipt)
    def execute_command(project_id: str, request: CommandRequest, http_request: Request) -> Receipt:
        _require_workspace(http_request, project_id)
        if hasattr(http_request.state, "actor"):
            request.actor = http_request.state.actor
        try:
            store.get_project(project_id)
        except KeyError as error:
            raise HTTPException(404, "project not found") from error
        duplicate = store.receipt_for_request(project_id, request.request_id)
        receipt = commands.execute(project_id, request, scopes=_scopes(http_request))
        project = store.get_project(project_id)
        if duplicate is None:
            runtime.emit(
                workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
                revision=project.revision, actor=receipt.actor,
                kind="command.denied" if receipt.status == ReceiptStatus.DENIED else "command.committed",
                payload={"command": receipt.command, "receipt_id": receipt.id, "reason": receipt.payload.get("reason")},
            )
        return receipt

    @application.post("/api/projects/{project_id}/commands/propose")
    def propose_commands(project_id: str, request: CommandProposalRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "project:read")
        return commands.propose(project_id, request)

    @application.post("/api/projects/{project_id}/commands/batch", response_model=Receipt)
    def execute_command_batch(project_id: str, request: CommandBatchRequest, http_request: Request) -> Receipt:
        _require_workspace(http_request, project_id)
        if hasattr(http_request.state, "actor"):
            request.actor = http_request.state.actor
        duplicate = store.receipt_for_request(project_id, request.request_id)
        receipt = commands.execute_batch(project_id, request, scopes=_scopes(http_request))
        project = store.get_project(project_id)
        if duplicate is None:
            runtime.emit(
                workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
                revision=project.revision, actor=receipt.actor,
                kind="command.denied" if receipt.status == ReceiptStatus.DENIED else "command.committed",
                payload={"command": receipt.command, "receipt_id": receipt.id, "command_count": len(request.commands)},
            )
        return receipt

    @application.post("/api/projects/{project_id}/confirmations")
    def create_confirmation(project_id: str, request: ConfirmationCreateRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        if getattr(http_request.state, "pairing_token", None) and getattr(http_request.state, "actor", "") != "browser":
            raise HTTPException(403, "human browser confirmation is required")
        declaration = COMMAND_REGISTRY.get(request.command)
        if declaration is None or declaration.confirmation_policy != "exact_human_confirmation":
            raise HTTPException(422, "command does not accept exact human confirmation")
        project = store.get_project(project_id)
        if project.revision != request.expected_revision:
            raise StaleRevisionError(request.expected_revision, project.revision)
        return store.create_confirmation(
            project_id, request.command, request.arguments, request.expected_revision,
            getattr(http_request.state, "actor", "browser"),
        )

    @application.post("/api/projects/{project_id}/renders", response_model=Receipt)
    def start_render(project_id: str, request: RenderRequest, http_request: Request) -> Receipt:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "render:run")
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
        runtime.emit(
            workspace_id=project.workspace_id or project.id, project_id=project.id, sequence_id=project.id,
            revision=project.revision, actor=actor, kind="job.state_changed",
            payload={"job_id": job_id, "state": "queued", "kind": "render"},
        )
        return receipt

    @application.get("/api/projects/{project_id}/spatial/snapshot")
    def get_spatial_snapshot(
        project_id: str, http_request: Request, focus_id: str | None = None,
        depth: str = Query("context", pattern="^(edit|context|system)$"),
        hop_count: int = Query(2, ge=0, le=6), entity_limit: int = Query(200, ge=10, le=1000),
        edge_limit: int = Query(400, ge=10, le=2000),
    ) -> dict:
        _require_workspace(http_request, project_id)
        return spatial.snapshot(
            project_id, focus_id=focus_id, depth=depth, hop_count=hop_count,
            entity_limit=entity_limit, edge_limit=edge_limit,
        ).model_dump(mode="json")

    @application.get("/api/projects/{project_id}/spatial/entities/{entity_id}/neighborhood")
    def get_spatial_neighborhood(
        project_id: str, entity_id: str, http_request: Request,
        hop_count: int = Query(2, ge=0, le=6), entity_limit: int = Query(200, ge=10, le=1000),
        edge_limit: int = Query(400, ge=10, le=2000),
    ) -> dict:
        _require_workspace(http_request, project_id)
        snapshot = spatial.neighborhood(
            project_id, entity_id, hop_count=hop_count,
            entity_limit=entity_limit, edge_limit=edge_limit,
        )
        if entity_id not in {entity.id for entity in snapshot.entities}:
            raise HTTPException(404, "spatial entity not found")
        return snapshot.model_dump(mode="json")

    @application.get("/api/projects/{project_id}/semantic/graph")
    def get_semantic_graph(
        project_id: str, http_request: Request, revision: int | None = Query(default=None, ge=1),
    ) -> dict:
        _require_workspace(http_request, project_id)
        try:
            return semantic_graph.graph(project_id, revision=revision).model_dump(mode="json")
        except (KeyError, ValueError) as error:
            raise HTTPException(409, "requested semantic revision is not retained") from error

    @application.post("/api/projects/{project_id}/semantic/neighborhood")
    def get_semantic_neighborhood(
        project_id: str, body: StructuralNeighborhoodRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        return semantic_graph.neighborhood(project_id, body).model_dump(mode="json")

    @application.get("/api/projects/{project_id}/journal")
    def list_journal_entries(
        project_id: str, http_request: Request, limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "journal:read")
        namespace = semantic_graph.graph(project_id).scope_uri
        return {
            "protocol_version": JOURNAL_PROTOCOL_VERSION, "namespace": namespace,
            "entries": [entry.model_dump(mode="json") for entry in journal.entries(namespace, limit=limit)],
        }

    @application.get("/api/projects/{project_id}/journal/verify")
    def verify_journal(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "journal:read")
        namespace = semantic_graph.graph(project_id).scope_uri
        return {
            "protocol_version": JOURNAL_PROTOCOL_VERSION, "namespace": namespace,
            "verification": journal.verify(namespace),
        }

    @application.post("/api/projects/{project_id}/journal/entries", status_code=201)
    def append_journal_entry(
        project_id: str, body: JournalEntryRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "journal:write")
        namespace = semantic_graph.graph(project_id).scope_uri
        try:
            entry, inserted = journal.append(namespace, body)
        except InadmissibleJournalPayload as error:
            raise HTTPException(422, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {
            "protocol_version": JOURNAL_PROTOCOL_VERSION, "inserted": inserted,
            "entry": entry.model_dump(mode="json"),
        }

    @application.get("/api/projects/{project_id}/spatial/entities/{entity_id}/blast-radius")
    def get_spatial_blast_radius(
        project_id: str, entity_id: str, http_request: Request,
        entity_limit: int = Query(200, ge=10, le=1000), edge_limit: int = Query(400, ge=10, le=2000),
    ) -> dict:
        _require_workspace(http_request, project_id)
        snapshot = spatial.blast_radius(
            project_id, entity_id, entity_limit=entity_limit, edge_limit=edge_limit,
        )
        if entity_id not in {entity.id for entity in snapshot.entities}:
            raise HTTPException(404, "spatial entity not found")
        return snapshot.model_dump(mode="json")

    @application.get("/api/projects/{project_id}/spatial/delta")
    def get_spatial_delta(
        project_id: str, http_request: Request, previous_revision: int = Query(ge=1),
        previous_cursor: int = Query(0, ge=0), previous_projection_hash: str | None = None,
    ) -> dict:
        _require_workspace(http_request, project_id)
        return spatial.delta(
            project_id, previous_revision=previous_revision, previous_cursor=previous_cursor,
            previous_projection_hash=previous_projection_hash,
        ).model_dump(mode="json")

    @application.post("/api/projects/{project_id}/spatial/frames", status_code=201)
    def declare_spatial_frame(
        project_id: str, body: SpatialFrameRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "focus:write")
        try:
            frame = spatial_frames.declare(
                project_id, body, actor=getattr(http_request.state, "actor", "studio-browser"),
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return frame.model_dump(mode="json")

    @application.get("/api/projects/{project_id}/spatial/frames/current")
    def get_current_spatial_frame(project_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            return spatial_frames.current(project_id).model_dump(mode="json")
        except KeyError as error:
            raise HTTPException(404, "spatial frame not found") from error

    @application.get("/api/projects/{project_id}/spatial/frames/{frame_id}")
    def get_spatial_frame(project_id: str, frame_id: str, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        try:
            return spatial_frames.get(project_id, frame_id).model_dump(mode="json")
        except KeyError as error:
            raise HTTPException(404, "spatial frame not found") from error

    @application.post("/api/projects/{project_id}/spatial/frames/{frame_id}/resolve")
    def resolve_spatial_frame_region(
        project_id: str, frame_id: str, body: SpatialRegionResolveRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        try:
            return spatial_frames.resolve(project_id, frame_id, body)
        except KeyError as error:
            raise HTTPException(404, "spatial frame not found") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @application.post("/api/projects/{project_id}/spatial/observations", status_code=201)
    def record_spatial_observation(
        project_id: str, body: SpatialObservationRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "focus:write")
        try:
            return spatial_frames.observe(
                project_id, body, actor=getattr(http_request.state, "actor", "studio-browser"),
            )
        except KeyError as error:
            raise HTTPException(404, "spatial frame not found") from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @application.get("/api/projects/{project_id}/runtime/events")
    def get_runtime_events(
        project_id: str, http_request: Request, cursor: int = Query(0, ge=0),
        limit: int = Query(200, ge=1, le=1000),
    ) -> dict:
        _require_workspace(http_request, project_id)
        oldest, newest = store.runtime_cursor_bounds(project_id)
        snapshot_required = bool(cursor and ((oldest is not None and cursor < oldest - 1) or (newest is not None and cursor > newest)))
        events = [] if snapshot_required else runtime.history(project_id, after_cursor=cursor, limit=limit)
        return {
            "project_id": project_id, "cursor": newest or 0, "snapshot_required": snapshot_required,
            "events": [event.model_dump(mode="json") for event in events],
        }

    @application.get("/api/projects/{project_id}/runtime/stream")
    async def stream_runtime_events(project_id: str, http_request: Request, cursor: int = Query(0, ge=0)):
        _require_workspace(http_request, project_id)
        header_cursor = http_request.headers.get("last-event-id", "").strip()
        if header_cursor:
            try:
                cursor = int(header_cursor)
            except ValueError:
                cursor = -1

        async def event_stream():
            nonlocal cursor
            generation = runtime.broker.generation
            oldest, newest = store.runtime_cursor_bounds(project_id)
            if cursor < 0 or (cursor and ((oldest is not None and cursor < oldest - 1) or (newest is not None and cursor > newest))):
                data = json.dumps({"reason": "invalid_or_pruned_cursor", "current_cursor": newest or 0})
                yield f"event: snapshot_required\nid: {newest or 0}\ndata: {data}\n\n"
                cursor = newest or 0
            while not await http_request.is_disconnected():
                events = runtime.history(project_id, after_cursor=cursor, limit=200)
                if events:
                    for event in events:
                        cursor = event.cursor
                        data = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
                        yield f"event: {event.kind}\nid: {event.cursor}\ndata: {data}\n\n"
                    continue
                yield ": keepalive\n\n"
                generation = await runtime.broker.wait(generation, timeout=10)

        return StreamingResponse(
            event_stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @application.post("/api/projects/{project_id}/spatial/directives")
    def post_spatial_directive(
        project_id: str, directive_request: SpatialDirectiveRequest, http_request: Request,
    ) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "focus:write")
        try:
            receipt, directive = directives.dispatch(
                project_id, directive_request, actor=getattr(http_request.state, "actor", "browser"),
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {"receipt": receipt.model_dump(mode="json"), "directive": directive.model_dump(mode="json")}

    @application.post("/api/spatial/directives/{receipt_id}/ack")
    def acknowledge_spatial_directive(
        receipt_id: str, ack: SpatialDirectiveAck, http_request: Request,
    ) -> dict:
        try:
            receipt = store.get_receipt(receipt_id)
        except KeyError as error:
            raise HTTPException(404, "directive receipt not found") from error
        _require_workspace(http_request, receipt.project_id)
        try:
            updated = directives.acknowledge(receipt_id, ack)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return updated.model_dump(mode="json")

    @application.post("/api/projects/{project_id}/shorts/jobs")
    def start_shorts_job(project_id: str, request: ShortsGenerateRequest, http_request: Request) -> dict:
        _require_workspace(http_request, project_id)
        _require_scope(http_request, "analysis:run")
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

    @application.get("/api/artifacts/{artifact_id}")
    def get_render_artifact_metadata(artifact_id: str, http_request: Request) -> dict:
        try:
            artifact = store.get_artifact(artifact_id)
        except KeyError as error:
            raise HTTPException(404, "render artifact not found") from error
        _require_workspace(http_request, artifact.project_id)
        return asdict(artifact)

    @application.get("/api/artifacts/{artifact_id}/content")
    def get_render_artifact(artifact_id: str, http_request: Request) -> FileResponse:
        try:
            artifact = store.get_artifact(artifact_id)
        except KeyError as error:
            raise HTTPException(404, "render artifact not found") from error
        _require_workspace(http_request, artifact.project_id)
        if artifact.managed_uri != f"sag-artifact://{artifact.id}":
            raise HTTPException(404, "invalid render artifact identity")
        try:
            path = renderer.path_for_artifact(artifact)
        except (FileNotFoundError, ValueError):
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
        project_id = request.project_id or request.workspace_id
        _require_workspace(http_request, project_id)
        try:
            project = store.get_project(project_id)
        except KeyError as error:
            raise HTTPException(404, "project not found") from error
        code, expires_at = store.start_pairing(
            store.workspace_for_project(project_id), project_id=project_id,
            sequence_id=request.sequence_id or project_id, scopes=request.scopes,
        )
        return {"code": code, "expires_at": expires_at}

    @application.post("/api/pairing/attach")
    def attach_pairing(request: PairAttachRequest) -> dict[str, Any]:
        try:
            token, expires_at, principal = store.attach_pairing(request.code, request.actor_name)
        except ValueError as error:
            raise HTTPException(401, str(error)) from error
        return {
            "access_token": token, "expires_at": expires_at,
            "workspace_id": principal["workspace_id"], "project_id": principal.get("project_id"),
            "sequence_id": principal.get("sequence_id"), "scopes": principal.get("scopes", []),
        }

    @application.post("/api/pairing/revoke")
    def revoke_pairing(http_request: Request) -> dict:
        token = getattr(http_request.state, "pairing_token", None)
        if not token:
            raise HTTPException(400, "request is not authenticated by a pairing token")
        store.revoke_token(token)
        return {"revoked": True}

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

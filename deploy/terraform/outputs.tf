output "web_url" { value = google_cloud_run_v2_service.web.uri }
output "engine_url" { value = google_cloud_run_v2_service.engine.uri }
output "dispatcher_url" { value = google_cloud_run_v2_service.dispatcher.uri }
output "media_bucket" { value = google_storage_bucket.media.name }
output "cloud_sql_instance" { value = google_sql_database_instance.postgres.connection_name }
output "artifact_repository" { value = google_artifact_registry_repository.images.name }

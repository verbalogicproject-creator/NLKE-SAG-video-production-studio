locals {
  prefix = "sag-${var.environment}"
  services = toset([
    "artifactregistry.googleapis.com", "cloudbuild.googleapis.com", "run.googleapis.com",
    "sqladmin.googleapis.com", "storage.googleapis.com", "cloudtasks.googleapis.com",
    "cloudscheduler.googleapis.com", "secretmanager.googleapis.com", "cloudkms.googleapis.com",
    "monitoring.googleapis.com", "logging.googleapis.com", "servicenetworking.googleapis.com",
    "vpcaccess.googleapis.com", "billingbudgets.googleapis.com"
  ])
  service_accounts = toset(["web", "engine", "dispatcher", "intake", "analysis", "render", "observer", "publisher", "task-invoker"])
  common_env = {
    GOOGLE_CLOUD_PROJECT = var.project_id
    GCP_REGION           = var.region
    STORAGE_BACKEND      = "gcs"
    QUEUE_BACKEND        = "cloud-tasks"
    GCS_MEDIA_BUCKET     = google_storage_bucket.media.name
    CLOUD_TASKS_QUEUE    = google_cloud_tasks_queue.dispatch.name
    YOUTUBE_KMS_KEY      = google_kms_crypto_key.youtube.id
  }
}

data "google_project" "current" {}

resource "google_project_service" "api" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "service" {
  for_each     = local.service_accounts
  account_id   = "${local.prefix}-${each.key}"
  display_name = "SAG ${var.environment} ${each.key}"
  depends_on   = [google_project_service.api]
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "${local.prefix}-images"
  format        = "DOCKER"
}

resource "google_storage_bucket" "media" {
  name                        = "${var.project_id}-${local.prefix}-media"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  public_access_prevention    = "enforced"
  versioning { enabled = true }
  lifecycle_rule {
    condition {
      age            = 7
      matches_prefix = ["staging/", "failed/"]
    }
    action { type = "Delete" }
  }
  lifecycle_rule {
    condition { num_newer_versions = 3 }
    action { type = "Delete" }
  }
}

resource "google_compute_network" "private" {
  name                    = "${local.prefix}-network"
  auto_create_subnetworks = false
}
resource "google_compute_subnetwork" "private" {
  name          = "${local.prefix}-subnet"
  ip_cidr_range = "10.42.0.0/24"
  region        = var.region
  network       = google_compute_network.private.id
}
resource "google_compute_global_address" "services" {
  name          = "${local.prefix}-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.private.id
}
resource "google_service_networking_connection" "private" {
  network                 = google_compute_network.private.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.services.name]
}
resource "google_vpc_access_connector" "run" {
  name          = "${local.prefix}-run"
  region        = var.region
  network       = google_compute_network.private.name
  ip_cidr_range = "10.43.0.0/28"
}

resource "google_sql_database_instance" "postgres" {
  name             = "${local.prefix}-postgres"
  region           = var.region
  database_version = "POSTGRES_16"
  deletion_protection = true
  settings {
    tier              = var.cloud_sql_tier
    availability_type = var.cloud_sql_ha ? "REGIONAL" : "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 20
    disk_autoresize   = true
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.private.id
      enable_private_path_for_google_cloud_services = true
    }
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
    maintenance_window {
      day          = 7
      hour         = 4
      update_track = "stable"
    }
  }
  depends_on = [google_service_networking_connection.private]
}
resource "google_sql_database" "chamber" {
  name     = "chamber"
  instance = google_sql_database_instance.postgres.name
}

resource "google_secret_manager_secret" "secret" {
  for_each  = toset(["database-url", "nextauth-secret", "google-client-id", "google-client-secret", "sag-service-token"])
  secret_id = "${local.prefix}-${each.key}"
  replication { auto {} }
}

resource "google_kms_key_ring" "main" {
  name     = local.prefix
  location = var.region
}
resource "google_kms_crypto_key" "youtube" {
  name            = "youtube-oauth"
  key_ring        = google_kms_key_ring.main.id
  rotation_period = "7776000s"
  lifecycle { prevent_destroy = true }
}

resource "google_cloud_tasks_queue" "dispatch" {
  name     = "${local.prefix}-dispatch"
  location = var.region
  rate_limits {
    max_concurrent_dispatches = 2
    max_dispatches_per_second = 2
  }
  retry_config {
    max_attempts  = 8
    min_backoff   = "5s"
    max_backoff   = "300s"
    max_doublings = 5
  }
}

resource "google_cloud_run_v2_service" "web" {
  name     = "${local.prefix}-web"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  template {
    service_account = google_service_account.service["web"].email
    vpc_access {
      connector = google_vpc_access_connector.run.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
    containers {
      image = var.web_image
      ports { container_port = 8080 }
      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env { name = "NODE_ENV" value = "production" }
      env { name = "CLOUD_RUN_INTAKE_JOB" value = google_cloud_run_v2_job.job["intake"].name }
      env { name = "CLOUD_RUN_ANALYSIS_JOB" value = google_cloud_run_v2_job.job["analysis"].name }
      env { name = "CLOUD_RUN_RENDER_JOB" value = google_cloud_run_v2_job.job["render"].name }
      env { name = "CLOUD_RUN_OBSERVER_JOB" value = google_cloud_run_v2_job.job["observer"].name }
      env { name = "CLOUD_RUN_PUBLISH_JOB" value = google_cloud_run_v2_job.job["publisher"].name }
      env { name = "SAG_ENGINE_URL" value = google_cloud_run_v2_service.engine.uri }
      env { name = "DISPATCH_URL" value = google_cloud_run_v2_service.dispatcher.uri }
      env { name = "TASK_INVOKER_SERVICE_ACCOUNT" value = google_service_account.service["task-invoker"].email }
      env {
        name = "DATABASE_URL"
        value_source { secret_key_ref { secret = google_secret_manager_secret.secret["database-url"].secret_id version = "latest" } }
      }
      env {
        name = "NEXTAUTH_SECRET"
        value_source { secret_key_ref { secret = google_secret_manager_secret.secret["nextauth-secret"].secret_id version = "latest" } }
      }
      env {
        name = "GOOGLE_CLIENT_ID"
        value_source { secret_key_ref { secret = google_secret_manager_secret.secret["google-client-id"].secret_id version = "latest" } }
      }
      env {
        name = "GOOGLE_CLIENT_SECRET"
        value_source { secret_key_ref { secret = google_secret_manager_secret.secret["google-client-secret"].secret_id version = "latest" } }
      }
      resources { limits = { cpu = "1", memory = "512Mi" } }
    }
  }
}

resource "google_cloud_run_v2_service" "engine" {
  name     = "${local.prefix}-engine"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  template {
    service_account = google_service_account.service["engine"].email
    vpc_access { connector = google_vpc_access_connector.run.id egress = "PRIVATE_RANGES_ONLY" }
    scaling { min_instance_count = 0 max_instance_count = 4 }
    containers {
      image = var.engine_image
      ports { container_port = 8080 }
      env { name = "SAG_VIDEO_START_ANALYSIS_WORKER" value = "0" }
      env { name = "SAG_VIDEO_START_RENDER_WORKER" value = "0" }
      env { name = "SAG_VIDEO_GCS_BUCKET" value = google_storage_bucket.media.name }
      env { name = "SAG_TRUST_CLOUD_RUN_IAM" value = "1" }
      env {
        name = "SAG_VIDEO_SERVICE_TOKEN"
        value_source { secret_key_ref { secret = google_secret_manager_secret.secret["sag-service-token"].secret_id version = "latest" } }
      }
      resources { limits = { cpu = "2", memory = "2Gi" } }
    }
  }
}

resource "google_cloud_run_v2_service" "dispatcher" {
  name     = "${local.prefix}-dispatcher"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  template {
    service_account = google_service_account.service["dispatcher"].email
    vpc_access { connector = google_vpc_access_connector.run.id egress = "PRIVATE_RANGES_ONLY" }
    containers {
      image = var.web_image
      ports { container_port = 8080 }
      dynamic "env" {
        for_each = local.common_env
        content { name = env.key value = env.value }
      }
      env { name = "CLOUD_RUN_INTAKE_JOB" value = google_cloud_run_v2_job.job["intake"].name }
      env { name = "CLOUD_RUN_ANALYSIS_JOB" value = google_cloud_run_v2_job.job["analysis"].name }
      env { name = "CLOUD_RUN_RENDER_JOB" value = google_cloud_run_v2_job.job["render"].name }
      env { name = "CLOUD_RUN_OBSERVER_JOB" value = google_cloud_run_v2_job.job["observer"].name }
      env { name = "CLOUD_RUN_PUBLISH_JOB" value = google_cloud_run_v2_job.job["publisher"].name }
      env {
        name = "DATABASE_URL"
        value_source { secret_key_ref { secret = google_secret_manager_secret.secret["database-url"].secret_id version = "latest" } }
      }
      resources { limits = { cpu = "1", memory = "512Mi" } }
    }
  }
}

locals {
  jobs = {
    intake    = { image = var.engine_image, sa = "intake", timeout = "1800s", memory = "2Gi", cpu = "2" }
    analysis  = { image = var.engine_image, sa = "analysis", timeout = "3600s", memory = "4Gi", cpu = "2" }
    render    = { image = var.engine_image, sa = "render", timeout = "3600s", memory = "8Gi", cpu = "4" }
    observer  = { image = var.engine_image, sa = "observer", timeout = "1800s", memory = "4Gi", cpu = "2" }
    publisher = { image = var.jobs_image, sa = "publisher", timeout = "3600s", memory = "1Gi", cpu = "1" }
  }
}
resource "google_cloud_run_v2_job" "job" {
  for_each = local.jobs
  name     = "${local.prefix}-${each.key}"
  location = var.region
  template {
    parallelism = 1
    task_count  = 1
    template {
      service_account = google_service_account.service[each.value.sa].email
      timeout         = each.value.timeout
      max_retries     = 0
      vpc_access { connector = google_vpc_access_connector.run.id egress = "PRIVATE_RANGES_ONLY" }
      containers {
        image = each.value.image
        env { name = "SAG_VIDEO_GCS_BUCKET" value = google_storage_bucket.media.name }
        env {
          name = "DATABASE_URL"
          value_source { secret_key_ref { secret = google_secret_manager_secret.secret["database-url"].secret_id version = "latest" } }
        }
        env {
          name = "GOOGLE_CLIENT_ID"
          value_source { secret_key_ref { secret = google_secret_manager_secret.secret["google-client-id"].secret_id version = "latest" } }
        }
        env {
          name = "GOOGLE_CLIENT_SECRET"
          value_source { secret_key_ref { secret = google_secret_manager_secret.secret["google-client-secret"].secret_id version = "latest" } }
        }
        env { name = "YOUTUBE_KMS_KEY" value = google_kms_crypto_key.youtube.id }
        resources { limits = { cpu = each.value.cpu, memory = each.value.memory } }
      }
    }
  }
}

resource "google_cloud_scheduler_job" "reconcile" {
  name      = "${local.prefix}-reconcile"
  region    = var.region
  schedule  = "*/2 * * * *"
  time_zone = "Etc/UTC"
  http_target {
    uri         = "${google_cloud_run_v2_service.dispatcher.uri}/api/internal/reconcile"
    http_method = "POST"
    oidc_token {
      service_account_email = google_service_account.service["task-invoker"].email
      audience                = google_cloud_run_v2_service.dispatcher.uri
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
resource "google_cloud_run_v2_service_iam_member" "dispatcher_tasks" {
  name     = google_cloud_run_v2_service.dispatcher.name
  location = var.region
  role     = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.service["task-invoker"].email}"
}
resource "google_cloud_run_v2_service_iam_member" "engine_web" {
  name     = google_cloud_run_v2_service.engine.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.service["web"].email}"
}
resource "google_project_iam_member" "cloudsql" {
  for_each = toset(["web", "engine", "intake", "analysis", "render", "observer", "publisher"])
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.service[each.key].email}"
}
resource "google_project_iam_member" "dispatcher_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.service["dispatcher"].email}"
}
resource "google_project_iam_member" "web_tasks" {
  project = var.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.service["web"].email}"
}
resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each = {
    for pair in setproduct(keys(google_secret_manager_secret.secret), ["web", "engine", "dispatcher", "intake", "analysis", "render", "observer", "publisher"]) :
    "${pair[0]}:${pair[1]}" => { secret = pair[0], service = pair[1] }
  }
  secret_id = google_secret_manager_secret.secret[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.service[each.value.service].email}"
}
resource "google_service_account_iam_member" "web_task_identity" {
  service_account_id = google_service_account.service["task-invoker"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.service["web"].email}"
}
resource "google_service_account_iam_member" "dispatcher_job_identity" {
  for_each           = toset(["intake", "analysis", "render", "observer", "publisher"])
  service_account_id = google_service_account.service[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.service["dispatcher"].email}"
}
resource "google_storage_bucket_iam_member" "media_access" {
  for_each = { web = "roles/storage.objectUser", engine = "roles/storage.objectUser", intake = "roles/storage.objectUser", analysis = "roles/storage.objectViewer", render = "roles/storage.objectUser", observer = "roles/storage.objectViewer", publisher = "roles/storage.objectViewer" }
  bucket = google_storage_bucket.media.name
  role   = each.value
  member = "serviceAccount:${google_service_account.service[each.key].email}"
}
resource "google_kms_crypto_key_iam_member" "youtube_web" {
  crypto_key_id = google_kms_crypto_key.youtube.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.service["web"].email}"
}
resource "google_kms_crypto_key_iam_member" "youtube_publisher" {
  crypto_key_id = google_kms_crypto_key.youtube.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.service["publisher"].email}"
}

resource "google_logging_metric" "failed_jobs" {
  name   = "${local.prefix}-failed-jobs"
  filter = "resource.type=\"cloud_run_job\" AND severity>=ERROR"
  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "Failed SAG jobs"
  }
}
resource "google_monitoring_alert_policy" "failed_jobs" {
  display_name = "${local.prefix} failed Cloud Run jobs"
  combiner     = "OR"
  conditions {
    display_name = "Any failed job"
    condition_threshold {
      filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.failed_jobs.name}\" AND resource.type=\"cloud_run_job\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
}

resource "google_billing_budget" "monthly" {
  count           = var.billing_account == "" ? 0 : 1
  billing_account = var.billing_account
  display_name    = "${local.prefix} monthly budget"
  amount {
    specified_amount { currency_code = "USD" units = tostring(var.monthly_budget_units) }
  }
  budget_filter { projects = ["projects/${data.google_project.current.number}"] }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.8 }
  threshold_rules { threshold_percent = 1.0 }
  all_updates_rule { disable_default_iam_recipients = false }
}

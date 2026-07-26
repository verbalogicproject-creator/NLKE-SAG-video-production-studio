variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "us-central1"
}
variable "environment" {
  type    = string
  default = "staging"
}
variable "web_image" { type = string }
variable "engine_image" { type = string }
variable "jobs_image" { type = string }
variable "domain" {
  type    = string
  default = ""
}
variable "cloud_sql_tier" {
  type    = string
  default = "db-custom-1-3840"
}
variable "cloud_sql_ha" {
  type    = bool
  default = false
}
variable "billing_account" {
  type    = string
  default = ""
}
variable "monthly_budget_units" {
  type    = number
  default = 250
}
variable "enable_cloud_execution" {
  type        = bool
  default     = false
  description = "Enable canonical heavy-job dispatch only after staging persistence/storage gates pass."
}
variable "external_beta_enabled" {
  type        = bool
  default     = false
  description = "Expose the web service publicly only after all production admission gates pass."
}
variable "transcription_base_url" {
  type        = string
  default     = ""
  description = "Whisper-compatible transcription API base URL used by the analysis job. Required for cloud acceptance unless the image includes whisper.cpp and a model."
}
variable "transcription_model" {
  type    = string
  default = "whisper-1"
}

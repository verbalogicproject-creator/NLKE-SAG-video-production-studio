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

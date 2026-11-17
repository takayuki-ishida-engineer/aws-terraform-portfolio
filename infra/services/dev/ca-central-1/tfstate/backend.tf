# The bootstrap root creates the State bucket, so it always keeps local State
# (docs/deployment-configuration.md section 3). Never add a backend override here.
terraform {
  backend "local" {}
}

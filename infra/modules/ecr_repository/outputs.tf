output "repositories" {
  description = "Per purpose: repository name, ARN and URL (<account>.dkr.ecr.<region>.amazonaws.com/<name>), for the operator's mirror copy. No credentials."
  value = { for purpose, repository in aws_ecr_repository.this : purpose => {
    name           = repository.name
    arn            = repository.arn
    repository_url = repository.repository_url
  } }
}

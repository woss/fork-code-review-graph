resource "aws_instance" "main" {
  ami           = "ami-123456"
  instance_type = "t2.micro"
}

module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  version = "3.0.0"
  
  name = var.vpc_name
}

variable "vpc_name" {
  description = "Name of the VPC"
  type        = string
  default     = "my-vpc"
}

output "instance_id" {
  value = aws_instance.main.id
}

data "aws_ami" "latest" {
  most_recent = true
  owners      = ["self"]
}

locals {
  common_tags = {
    Project = "test"
  }
}

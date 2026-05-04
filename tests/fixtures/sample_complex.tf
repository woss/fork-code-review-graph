# Complex Terraform file with nested blocks
terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_instance" "web" {
  ami           = "ami-12345678"
  instance_type = "t2.micro"

  root_block_device {
    volume_size = 50
    volume_type = "gp3"
  }

  ebs_block_device {
    device_name = "/dev/sdf"
    volume_size = 100
  }

  tags = {
    Name = "WebServer"
    Environment = "Production"
  }
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"

  tags {
    Name = "MainVPC"
  }
}

module "database" {
  source = "terraform-aws-modules/rds/aws"
  version = "5.0.0"

  identifier = "mydb"
  
  engine            = "postgres"
  engine_version    = "14.0"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
}

variable "environment" {
  type    = string
  default = "dev"
}

output "web_instance_id" {
  value = aws_instance.web.id
}

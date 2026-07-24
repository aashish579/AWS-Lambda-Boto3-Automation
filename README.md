# AWS Lambda & Boto3 Automation Projects

![AWS](https://img.shields.io/badge/AWS-Lambda-orange)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Boto3](https://img.shields.io/badge/Boto3-Automation-green)
![IAM](https://img.shields.io/badge/IAM-Least%20Privilege-red)

## Project Overview

This repository contains six AWS automation projects developed using **AWS Lambda**, **Python (Boto3)** and various AWS services including Amazon EC2, Amazon EBS, Amazon S3, Amazon SNS, Amazon EventBridge, IAM and CloudWatch.

The objective of these projects is to automate common cloud administration and security tasks using serverless computing while following AWS best practices and the Principle of Least Privilege.

---

## AWS Services Used

- AWS Lambda
- Amazon EC2
- Amazon EBS
- Amazon S3
- Amazon SNS
- Amazon EventBridge Scheduler
- Amazon CloudWatch
- AWS IAM
- AWS Cost Explorer

---

## Completed Projects

### Assignment 1
Automated S3 Bucket Cleanup

- Delete objects older than 30 days
- Pagination support
- Least privilege IAM
- CloudWatch logging

---

### Assignment 2
Automated EBS Snapshot Creation & Cleanup

- Snapshot creation
- Snapshot tagging
- Automatic cleanup
- Weekly scheduling

---

### Assignment 3
Auto Tagging EC2 Instances

- EventBridge trigger
- Automatic tagging
- LaunchDate
- Owner
- Environment

---

### Assignment 4
Daily AWS Cost Alert

- Cost Explorer API
- SNS Email Alert
- EventBridge Scheduler
- Threshold monitoring

---

### Assignment 5
Restore EC2 Instance From Latest Snapshot

- Latest snapshot discovery
- Automatic AMI registration
- EC2 launch
- Disaster Recovery automation

---

### Assignment 6
Audit S3 Buckets For Public Access

- Block Public Access verification
- Bucket Policy Status
- ACL inspection
- SNS Security Alert

---

## Repository Structure

```text
Assignment-01-S3-Bucket-Cleanup
Assignment-02-EBS-Snapshot-Automation
Assignment-03-EC2-Auto-Tagging
Assignment-04-AWS-Cost-Alert
Assignment-05-EC2-Restore
Assignment-06-S3-Public-Access-Audit
Documentation
```

---

## Technologies

- Python 3.12
- Boto3
- AWS Lambda
- IAM
- EventBridge
- SNS
- CloudWatch
- EC2
- EBS
- S3

---

## Author

**Aashish Gautam**

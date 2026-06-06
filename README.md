# Real-Time AWS Cost Alert System

An automated serverless solution that analyzes AWS cost data from S3, detects cost spikes using statistical analysis, and sends email alerts via SNS.

---

## Architecture
<img width="1774" height="887" alt="ChatGPT Image Jun 6, 2026, 02_27_53 PM" src="https://github.com/user-attachments/assets/4b95a0b4-0a5f-445c-bfd0-9e95ad8f0c3a" />



##  Features

-  **Auto-triggered** on CSV upload to S3
-  **Total cost spike detection** using median-based thresholding
-  **Per-service spike detection** (EC2, S3, CloudWatch, VPC, etc.)
-  **Email alerts** via Amazon SNS with spike details and % change
-  **Fallback summary email** even when no spikes are detected

---

##  Project Structure

```
├── lambda_function.py       # Main Lambda handler
├── README.md                # Project documentation
```

---

##  Prerequisites

- AWS Account
- Python 3.12
- AWS CLI configured
- An S3 bucket for cost CSV files
- An SNS topic with a confirmed email subscription

---

## Setup & Deployment

### Step 1: Create S3 Bucket

```bash
aws s3 mb s3://your-cost-analysis-bucket
```

### Step 2: Create SNS Topic & Subscribe Your Email

```bash
# Create topic
aws sns create-topic --name your-cost-alerts-topic

# Subscribe your email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:your-cost-alerts-topic \
  --protocol email \
  --notification-endpoint your@email.com
```

>  **Check your inbox and click the confirmation link** — emails won't arrive until confirmed.

### Step 3: Create Lambda Function

1. Go to **AWS Lambda** → **Create function**
2. Choose **Author from scratch**
3. Runtime: **Python 3.12**
4. Upload `lambda_function.py` as a ZIP with dependencies

### Step 4: Add Environment Variable

| Key | Value |
|---|---|
| `SNS_TOPIC_ARN` | `arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:your-cost-alerts-topic` |

### Step 5: Add S3 Trigger

1. In Lambda → **Add trigger**
2. Select **S3**
3. Choose your bucket
4. Event type: **PUT** (on upload)

### Step 6: Configure IAM Role Permissions

Attach the following permissions to your Lambda's IAM role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3Read",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::your-cost-analysis-bucket",
        "arn:aws:s3:::your-cost-analysis-bucket/*"
      ]
    },
    {
      "Sid": "AllowSNSPublish",
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:your-cost-alerts-topic"
    },
    {
      "Sid": "AllowLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "*"
    }
  ]
}
```

> ⚠️ If a **Permissions Boundary** is set on the role, make sure it also includes `sns:Publish` and `s3:GetObject` — otherwise the boundary will block those actions even if the policy allows them.

---

## 📄 CSV Format

Your CSV file should follow this structure:

| Service | EC2 Instances($) | S3($) | CloudWatch($) | VPC($) | Total Costs($) |
|---|---|---|---|---|---|
| 2024-01-01 | 12.50 | 1.20 | 0.50 | 0.30 | 14.50 |
| 2024-01-02 | 15.00 | 1.50 | 0.60 | 0.30 | 17.40 |
| Service total | 27.50 | 2.70 | 1.10 | 0.60 | 31.90 |

**Notes:**
- The `Service` column should contain dates
- `Service total` summary rows are automatically filtered out
- Column names are matched **case-insensitively** and whitespace is stripped
- Tax columns are automatically excluded from analysis

---

## 📧 Sample Email Alert

<img width="597" height="211" alt="image" src="https://github.com/user-attachments/assets/1a43e5dd-63a5-48d6-b2da-56ea4f598590" />


## Configuration

You can adjust the spike sensitivity inside `lambda_function.py`:

```python
SPIKE_MULTIPLIER = 0.0   # 0.0 = any value above median triggers spike
MIN_SPIKE_AMOUNT = 0.01  # minimum dollar amount to be flagged
```

| Value | Sensitivity |
|---|---|
| `0.0` | Very high — flags anything above median |
| `0.5` | Medium — flags 50% above median |
| `1.5` | Low — standard IQR-based detection |

---

## 🐛 Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `Runtime.ImportModuleError` for numpy | Python version mismatch | Set Lambda runtime to **Python 3.12** |
| `AccessDenied` on S3 GetObject | Missing IAM permission | Add `s3:GetObject` to Lambda role |
| `AuthorizationError` on SNS Publish | Missing IAM permission or boundary | Add `sns:Publish` and check permissions boundary |
| `'Total Costs($)' column not found` | Column name mismatch | Code auto-detects — check CloudWatch logs for actual column names |
| No email received | SNS subscription not confirmed | Check inbox for confirmation email and click the link |
| `Unknown datetime string format` | Summary rows in CSV | Fixed — rows like `Service total` are filtered automatically |

---

##  Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pandas` | latest | CSV parsing and data manipulation |
| `numpy` | latest | Statistical spike detection |
| `boto3` | built-in | AWS S3 and SNS SDK |

Install dependencies for deployment package:

```bash
pip install pandas numpy -t ./package/ \
  --python-version 3.12 \
  --platform manylinux2014_x86_64 \
  --only-binary=:all:
```

---

##  License

MIT License — free to use and modify.

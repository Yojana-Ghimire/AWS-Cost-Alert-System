import json
import boto3
import io
import numpy as np
import pandas as pd
import os

s3 = boto3.client("s3")
sns = boto3.client("sns")


SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', 'arn:aws:sns:us-east-1:545009833265:mysnstopic')

def lambda_handler(event, context):
    try:
        # 1. Get bucket and file information
        bucketname = event["Records"][0]["s3"]["bucket"]["name"]
        bucketobject = event["Records"][0]["s3"]["object"]["key"]

        # 2. Fetch the CSV data
        response = s3.get_object(Bucket=bucketname, Key=bucketobject)
        data = response["Body"].read().decode("utf-8")

        # 3. Load into DataFrame and normalize column names
        df = pd.read_csv(io.StringIO(data))
        df.columns = df.columns.str.strip()
        print(f"Columns: {df.columns.tolist()}")
        print(f"First few rows:\n{df.head()}")

        # 4. Dynamically find key columns (case-insensitive)
        date_col = next((c for c in df.columns if c.lower() == 'service'), None)
        total_col = next((c for c in df.columns if 'total' in c.lower() and 'cost' in c.lower()), None)
        tax_col = next((c for c in df.columns if 'tax' in c.lower()), None)

        if not date_col:
            raise ValueError(f"'Service' column not found. Available: {df.columns.tolist()}")
        if not total_col:
            raise ValueError(f"'Total Costs' column not found. Available: {df.columns.tolist()}")

        print(f"Using → Date col: '{date_col}', Total col: '{total_col}', Tax col: '{tax_col}'")

        # 5. Filter out summary rows and parse dates safely
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        daily_costs_df = df[df[date_col].notna()].copy()

        if tax_col:
            daily_costs_df = daily_costs_df.drop(columns=[tax_col], errors='ignore')

        daily_costs_df = daily_costs_df.sort_values(by=date_col).reset_index(drop=True)

        # 6. Convert all cost columns to numeric safely
        cost_cols = [col for col in daily_costs_df.columns if col != date_col]
        for col in cost_cols:
            daily_costs_df[col] = pd.to_numeric(daily_costs_df[col], errors='coerce').fillna(0)

        print(f"Rows after filtering: {len(daily_costs_df)}")
        print(f"Total costs preview:\n{daily_costs_df[[date_col, total_col]]}")

        email_body = ""

        # --- ANALYSIS PART 1: TOTAL COST SPIKES ---
        total_costs = daily_costs_df[total_col].values

        # ✅ VERY LOW THRESHOLD — triggers on almost any cost increase
        SPIKE_MULTIPLIER = 0.0   # 0.0 = any value above median triggers spike
        MIN_SPIKE_AMOUNT = 0.01  # minimum $0.01 to be considered a spike

        median_total = np.median(total_costs)
        upper_bound_total = median_total * (1 + SPIKE_MULTIPLIER)

        print(f"Total cost median: {median_total}, upper bound: {upper_bound_total}")

        daily_costs_df['Total_Pct_Change'] = daily_costs_df[total_col].pct_change() * 100
        daily_costs_df['Is_Spike'] = (
            (daily_costs_df[total_col] > upper_bound_total) &
            (daily_costs_df[total_col] >= MIN_SPIKE_AMOUNT)
        )

        total_spikes = daily_costs_df[daily_costs_df['Is_Spike']]
        print(f"Total spikes found: {len(total_spikes)}")

        if not total_spikes.empty:
            email_body += "=================== Total Cost Spikes ========================\n"
            for _, row in total_spikes.iterrows():
                pct_str = f"{row['Total_Pct_Change']:.2f}%" if not pd.isna(row['Total_Pct_Change']) else "N/A"
                email_body += (
                    f"Date: {row[date_col].date()}, "
                    f"Amount: ${row[total_col]:.2f}, "
                    f"Increase from Prev Day: {pct_str}\n"
                )

        # --- ANALYSIS PART 2: INDIVIDUAL SERVICE-WISE SPIKES ---
        service_cols = [
            col for col in daily_costs_df.columns
            if col not in [date_col, total_col, 'Is_Spike', 'Total_Pct_Change']
        ]

        svc_email_section = "\n=================== Cost Spikes for Services ========================\n"
        svc_spike_found = False

        for col in service_cols:
            col_values = daily_costs_df[col].values
            median_svc = np.median(col_values)

            # ✅ VERY LOW THRESHOLD per service
            upper_bound_svc = median_svc * (1 + SPIKE_MULTIPLIER)

            pct_col_name = f"{col}_Pct_Change"
            daily_costs_df[pct_col_name] = daily_costs_df[col].pct_change() * 100

            svc_spikes = daily_costs_df[
                (daily_costs_df[col] > upper_bound_svc) &
                (daily_costs_df[col] >= MIN_SPIKE_AMOUNT)
            ]

            if not svc_spikes.empty:
                svc_spike_found = True
                for _, row in svc_spikes.iterrows():
                    pct_str = f"{row[pct_col_name]:.2f}%" if not pd.isna(row[pct_col_name]) else "N/A"
                    svc_email_section += (
                        f"{col} Spike → "
                        f"Date: {row[date_col].date()}, "
                        f"Amount: ${row[col]:.2f}, "
                        f"Increase: {pct_str}\n"
                    )

        if svc_spike_found:
            email_body += svc_email_section

        # --- FALLBACK: Send email with full summary if no spikes detected ---
        if not email_body:
            email_body = "=================== AWS Cost Summary (No Spikes) ========================\n"
            email_body += f"Total rows analyzed: {len(daily_costs_df)}\n"
            email_body += f"Date range: {daily_costs_df[date_col].min().date()} to {daily_costs_df[date_col].max().date()}\n"
            email_body += f"Min cost: ${daily_costs_df[total_col].min():.2f}\n"
            email_body += f"Max cost: ${daily_costs_df[total_col].max():.2f}\n"
            email_body += f"Average cost: ${daily_costs_df[total_col].mean():.2f}\n\n"
            email_body += "Daily Breakdown:\n"
            for _, row in daily_costs_df.iterrows():
                email_body += f"  {row[date_col].date()}: ${row[total_col]:.2f}\n"

        # --- SEND EMAIL VIA SNS ---
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"AWS Cost Alert - {bucketobject}",
            Message=email_body
        )
        print("SNS alert sent.")

        return {
            'statusCode': 200,
            'body': json.dumps('Analysis completed and alert sent.')
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': str(e)})}
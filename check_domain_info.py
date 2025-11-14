import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
import oss2

# Load config
config = Config()
access_key_id = config.get('scrapers.bilibili.oss_access_key_id')
access_key_secret = config.get('scrapers.bilibili.oss_access_key_secret')
bucket_name = config.get('oss.bucket')
endpoint = config.get('oss.endpoint')

# Create OSS client
auth = oss2.Auth(access_key_id, access_key_secret)
bucket = oss2.Bucket(auth, endpoint, bucket_name)

print("Bucket Domain Information:")
print("="*60)

# Get bucket info
info = bucket.get_bucket_info()
print(f"Bucket Name: {info.name}")
print(f"Region: {info.location}")
print(f"Intranet Endpoint: {info.intranet_endpoint}")
print(f"Extranet Endpoint: {info.extranet_endpoint}")

print("\n" + "="*60)
print("Available Access Methods:")
print("\n1. Regular OSS Endpoint (forces download for HTML):")
print(f"   https://{bucket_name}.{endpoint.replace('https://', '').replace('http://', '')}/research-reports/report_20251110_192142.html")

print("\n2. To enable inline viewing, you need to:")
print("   a) Go to OSS Console: https://oss.console.aliyun.com/")
print(f"   b) Select bucket: {bucket_name}")
print("   c) Go to: Transmission -> Domain Names")
print("   d) Check if there's a 'Static Website Endpoint' listed")
print("   e) Or bind a custom domain for website hosting")

print("\n3. Alternative: Use signed URLs with response-content-disposition parameter")
print("   (But this requires authentication, not fully public)")

print("\n" + "="*60)
print("Current Status: Static website hosting is ENABLED")
print("But website endpoint DNS may not be activated yet.")
print("\nRecommendation: Check OSS Console -> Domain Names section")



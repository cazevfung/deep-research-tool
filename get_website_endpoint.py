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

print("Getting Website Endpoint Information...")
print("="*60)

try:
    website_config = bucket.get_bucket_website()
    print("✅ Website Hosting is enabled!")
    print(f"  Index Document: {website_config.index_file}")
    print(f"  Error Document: {website_config.error_file}")
    
    # Calculate website endpoint
    # Format: http://<BucketName>.oss-website-<Region>.aliyuncs.com
    region = 'cn-beijing'  # Extract from endpoint
    website_endpoint = f"http://{bucket_name}.oss-website-{region}.aliyuncs.com"
    
    print(f"\n📎 Website Endpoint URL Format:")
    print(f"  {website_endpoint}/research-reports/report_20251110_192142.html")
    print(f"\nℹ️  Use this URL format for HTML files to display in browser!")
    
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "="*60)
print("Note: Website endpoints use HTTP, not HTTPS")
print("They serve files for viewing, not downloading")



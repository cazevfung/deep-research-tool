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

print(f"Enabling Static Website Hosting for: {bucket_name}")
print("="*60)

try:
    # Enable static website hosting
    # This makes OSS serve HTML files for viewing instead of download
    website_config = oss2.models.BucketWebsite('index.html', 'error.html')
    bucket.put_bucket_website(website_config)
    
    print("✅ Static Website Hosting enabled!")
    print("\nConfiguration:")
    print("  Index Document: index.html")
    print("  Error Document: error.html")
    print("\nThis allows HTML files to be viewed in browser instead of downloaded.")
    print("\n" + "="*60)
    print("Test your URL again - it should now display in browser!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\nIf this fails, you may need to enable it manually in OSS Console:")
    print("  1. Go to https://oss.console.aliyun.com/")
    print("  2. Select bucket: youliaodao-deep-research")
    print("  3. Go to: Basic Settings -> Static Pages")
    print("  4. Click 'Configure' and enable Static Website Hosting")
    print("  5. Set Index Document: index.html")
    print("  6. Set Error Document: error.html")



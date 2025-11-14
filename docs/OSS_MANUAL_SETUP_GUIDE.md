# Manual OSS Bucket Setup for Public Reports

## Problem

Your OSS bucket has security restrictions that prevent programmatic configuration of public access. You'll see errors like:
- `Put public object acl is not allowed`
- `Put public bucket policy is not allowed`

This is actually a good security feature! It means you need to use the Alibaba Cloud Console with your root account or a properly permissioned RAM user.

## Solution: Manual Setup via OSS Console

### Step 1: Log into OSS Console

1. Visit: https://oss.console.aliyun.com/
2. Log in with your Alibaba Cloud account (use root account if RAM user lacks permissions)
3. Select your bucket: **transcription-services** (or your configured bucket name)

### Step 2: Configure Public Read Access

You have two options:

#### Option A: Bucket-Level ACL (Simplest)

1. Click on your bucket **transcription-services**
2. Go to **Access Control** → **Bucket ACL**
3. Change from **Private** to **Public Read**
4. Click **Save**

✅ **Done!** All files in the bucket are now publicly readable.

#### Option B: Bucket Policy (More Secure - Recommended)

Only makes the `research-reports/` folder public, keeping other files private.

1. Click on your bucket **transcription-services**
2. Go to **Access Control** → **Bucket Policy**  
3. Click **Authorize** or **Add Authorization**
4. Use **Graphical Setups** mode:
   - **Applied Resources**: Choose **Specified Resources**
     - Enter: `research-reports/*`
   - **Authorized Users**: Choose **All Users (Public)**
   - **Authorized Operation**: Select **GetObject** (Read only)
   - Click **OK**

Or use **Policy Syntax** mode and paste:

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": ["*"],
      "Action": ["oss:GetObject"],
      "Resource": ["acs:oss:*:*:transcription-services/research-reports/*"]
    }
  ]
}
```

Replace `transcription-services` with your actual bucket name.

✅ **Done!** Only files in `research-reports/` are publicly readable.

### Step 3: Verify Access

1. Upload a test file:
   ```bash
   python scripts/generate_export_html.py 20251110_192142 --upload
   ```

2. Copy the URL from output:
   ```
   📎 Public URL: https://transcription-services.oss-cn-beijing.aliyuncs.com/research-reports/report_20251110_192142.html
   ```

3. Test in **incognito/private browser window** (to ensure no authentication is used)

4. If the HTML loads successfully: **✅ Success!**

5. If you see XML error "AccessDenied": Go back and verify Step 2 settings

### Step 4: (Optional) Disable Bucket Access Control Blocks

If Option A and B don't work, your bucket might have "Block Public Access" enabled:

1. In OSS Console, go to your bucket
2. Navigate to **Access Control** → **Block Public Access**
3. If enabled, you'll see blocks for:
   - Block public ACLs
   - Block public bucket policies
4. **Disable** these blocks if you want to allow public access
5. Try Step 2 again

⚠️ **Security Note:** Only disable if you understand the implications and trust the upload process.

## Testing Your Setup

### Quick Test

Open this URL in incognito mode (replace with your bucket name):
```
https://transcription-services.oss-cn-beijing.aliyuncs.com/research-reports/report_20251110_192142.html
```

Expected result:
- ✅ **Success**: HTML page loads with your research report
- ❌ **Failure**: XML error page with "AccessDenied"

### Full Workflow Test

```bash
# 1. Generate and upload
python scripts/generate_export_html.py 20251110_192142 --upload

# 2. Copy the public URL from output

# 3. Share with a friend or open in incognito mode

# 4. Verify they can access without any login
```

## Troubleshooting

### Issue: Still Getting AccessDenied After Setup

**Possible causes:**
1. **Wrong bucket name** - Verify in config.yaml matches OSS console
2. **Wrong region** - Check endpoint matches bucket region
3. **Bucket policy syntax error** - Copy exact JSON from above
4. **Cache** - Try in fresh incognito window
5. **Block Public Access** still enabled - See Step 4 above

**Solution:** Double-check all settings in OSS Console

### Issue: Can't Modify Bucket Settings (Permission Denied)

**Cause:** Your RAM user access key doesn't have permissions

**Solution:**
1. Log in with **root account** (master account)
2. Or grant RAM user these permissions:
   - `oss:PutBucketAcl`
   - `oss:PutBucketPolicy`
   - `oss:GetBucketAcl`
   - `oss:GetBucketPolicy`

### Issue: Security Team Won't Allow Public Bucket

**Solution:** Use signed URLs instead (temporary access):

The upload service already uploads files. To share them securely:

```python
from scrapers.bilibili_scraper import BilibiliScraper

# Use Bilibili scraper's signed URL method
scraper = BilibiliScraper()
signed_url = scraper._generate_signed_url(
    bucket_name='transcription-services',
    object_key='research-reports/report_20251110_192142.html',
    access_key_id='YOUR_KEY',
    access_key_secret='YOUR_SECRET',
    expires=604800  # 7 days
)

print(f"Temporary URL (expires in 7 days): {signed_url}")
```

## Summary

1. ✅ **Files upload successfully** - The upload service works!
2. ❌ **Programmatic ACL config blocked** - Expected security restriction
3. ✅ **Manual config in console** - Simple 2-minute process
4. ✅ **Share public URLs** - Anyone with link can access

After manual setup (one time only), all future uploads will be publicly accessible! 🎉

## Quick Reference

| Task | Command |
|------|---------|
| Generate + Upload | `python scripts/generate_export_html.py <session_id> --upload` |
| Upload only (file exists) | `python scripts/generate_export_html.py --upload-only` |
| Test URL | Open in incognito: `https://your-bucket.oss-cn-beijing.aliyuncs.com/research-reports/...` |

## Need Help?

1. Check Alibaba Cloud OSS docs: https://www.alibabacloud.com/help/en/oss/
2. Review OSS console: https://oss.console.aliyun.com/
3. Check this project's docs: `docs/OSS_SETUP_FOR_PUBLIC_REPORTS.md`



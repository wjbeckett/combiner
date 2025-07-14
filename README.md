# Combiner 🎬

Seamlessly combine your 4K collection with intelligent library optimization.

## 🚀 What Combiner Does

Combiner automatically processes your 4K movie downloads and intelligently combines them with your existing media library, creating perfect Plex quality selection while optimizing storage with hardlinks.

## ✨ The Magic Process

1. **4K movie downloads** → Combiner receives webhook from 4K Radarr
2. **Scans your library** → Finds existing movie versions
3. **Optimizes existing files** → Renames with quality suffix (e.g., `- 1080p`)
4. **Creates 4K hardlink** → Adds with quality suffix (e.g., `- 2160p`)
5. **Cleans up tracking** → Removes from 4K Radarr instance
6. **Perfect Plex integration** → Quality selection dropdown appears!

## 📁 Before & After

**Before Combiner:**
```
/Movies/Top Gun Maverick (2022)/
  Top Gun Maverick (2022).mkv                    # 1080p, no quality info
```

**After Combiner Processing:**
```
/Movies/Top Gun Maverick (2022)/
  Top Gun Maverick (2022) - 1080p.mkv           # Auto-renamed existing!
  Top Gun Maverick (2022) - 2160p.mkv           # New 4K hardlink
```

**Result in Plex:**
- Single movie entry with quality selection dropdown
- Choose between 1080p and 2160p on-the-fly
- Zero duplicate storage (hardlinks, not copies!)

## 🛠️ Quick Setup

### 1. Create Config Directory

```bash
# Create config directory on your host
mkdir -p /mnt/user/appdata/combiner

# Copy example config
curl -o /mnt/user/appdata/combiner/config.yml \
  https://raw.githubusercontent.com/yourusername/combiner/main/config.yml.example

# Edit with your settings
nano /mnt/user/appdata/combiner/config.yml
```

### 2. Deploy with Docker Compose

```yaml
version: '3.8'

services:
  combiner:
    image: ghcr.io/yourusername/combiner:latest
    container_name: combiner
    restart: unless-stopped
    ports:
      - "5465:5465"
    volumes:
      - /mnt/user/data:/data # Same data mount as your Radarr and Radarr-4k
      - /mnt/user/appdata/combiner:/config  # Config & logs
    networks:
      - media
```

```bash
docker-compose up -d
```

### 3. Configure 4K Radarr Webhook

In your **4K Radarr instance**:

1. **Settings** → **Connect** → **Add Webhook**
2. **URL**: `http://combiner:5465/webhook/radarr-4k`
3. **Triggers**: Enable **On Import**
4. **Test** the connection
5. **Save**

### 4. Download a 4K Movie

Watch Combiner automatically:
- ✅ Process the webhook
- ✅ Find your existing 1080p version
- ✅ Rename it with quality suffix
- ✅ Create 4K hardlink with quality suffix
- ✅ Remove from 4K Radarr
- ✅ Perfect Plex quality selection!

## ⚙️ Configuration

### Config Directory Structure
```
/mnt/user/appdata/combiner/
├── config.yml          # Main configuration
└── combiner.log        # Application logs (auto-created)
```

### config.yml
```yaml
radarr:
  main:
    url: "http://radarr:7878"
    api_key: "your-main-radarr-api-key"
  k4:
    url: "http://radarr4k:7878"  
    api_key: "your-4k-radarr-api-key"

plex_naming:
  enabled: true                    # Enable Plex optimization
  add_quality_suffix: true         # Add quality suffixes for merging
```

### Environment Variables (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `RADARR_MAIN_URL` | Main Radarr URL | - |
| `RADARR_MAIN_API_KEY` | Main Radarr API key | - |
| `RADARR_4K_URL` | 4K Radarr URL | - |
| `RADARR_4K_API_KEY` | 4K Radarr API key | - |
| `ENABLE_PLEX_NAMING` | Enable Plex naming | `false` |
| `PLEX_QUALITY_SUFFIX` | Add quality suffixes | `false` |

## 🔍 Monitoring & Debugging

### Health Check
```bash
curl http://localhost:5465/health
```

### View Configuration
```bash
curl http://localhost:5465/config
```

### Quality Mappings
```bash
curl http://localhost:5465/quality-mappings
```

### Recent Logs
```bash
curl http://localhost:5465/logs
```

### Log Files
- **Container logs**: `docker logs combiner`
- **Application logs**: `/mnt/user/appdata/combiner/combiner.log`

## 🎯 Key Features

### 🧠 Intelligent Quality Detection
- Automatically detects quality from existing filenames
- Maps Radarr qualities to Plex-friendly names
- Defaults to 1080p for undetected files

### 🔗 Smart Hardlink Management  
- Creates hardlinks (not copies) to save storage
- Maintains file permissions and metadata
- Works across same filesystem only

### 🏷️ Automatic File Optimization
- Renames existing files for Plex compatibility
- Adds quality suffixes for perfect merging
- Skips files that already have suffixes

### 🗑️ Clean Radarr Management
- Removes processed movies from 4K instance
- Prevents duplicate tracking
- Maintains clean library organization

### 📝 Comprehensive Logging
- File-based logging in config directory
- Real-time log viewing via API
- Detailed processing information

## 📋 Requirements

- **Two Radarr instances** (main library + 4K)
- **Shared storage** accessible by both containers
- **Same filesystem** for hardlink support (ext4, NTFS, etc.)
- **Docker** and **docker-compose**

## 🎬 Supported Formats

- `.mkv`, `.mp4`, `.avi`, `.m4v`, `.mov`
- `.wmv`, `.flv`, `.webm`, `.ts`, `.m2ts`

## 🚨 Important Notes

- **Test first!** Try with one movie before bulk processing
- **Same filesystem required** for hardlinks to work
- **Backup your config** before making changes
- **Monitor logs** during initial setup

## 🎉 Perfect For

- **Plex users** wanting seamless quality selection
- **Storage optimizers** avoiding duplicate files
- **Automation enthusiasts** eliminating manual work
- **Library perfectionists** wanting consistent naming

## 🚀 Why Combiner Changes Everything

**Before Combiner:**
- Manual file management for every 4K download
- Inconsistent naming across your library  
- Duplicate storage eating your drives
- No quality selection in Plex

**After Combiner:**
- ✅ **Zero manual work** - Everything automated
- ✅ **Perfect Plex integration** - Quality selection just works
- ✅ **Optimized storage** - Hardlinks save space
- ✅ **Library enhancement** - Existing files get optimized too
- ✅ **Comprehensive logging** - Full visibility into operations

## 🎬 Deploy Once. Enjoy Forever.

Combiner transforms your media workflow from tedious manual management to seamless automation. Every 4K download makes your library better!

**Ready to combine your collection?** 🚀✨

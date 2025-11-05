# GitHub Pages Setup Instructions

## 🌐 Making Your Weather Presentation Publicly Accessible

Your weather presentation is now ready to be published on GitHub Pages! Follow these steps to make it publicly accessible.

---

## 📋 Quick Setup (5 minutes)

### Step 1: Merge to Main Branch (Recommended)

Since GitHub Pages typically works best from the main branch, you should merge your work:

1. **Go to GitHub.com**
   - Navigate to: https://github.com/monksealseal/tinypets

2. **Create a Pull Request**
   - Click "Pull requests" tab
   - Click "New pull request"
   - Base: `main` or `master`
   - Compare: `claude/concord-nh-weather-presentation-011CUoUZ41jzMR1u6ituKvCx`
   - Click "Create pull request"
   - Add title: "Add Weather Presentation for Concord, NH"
   - Click "Create pull request"

3. **Merge the Pull Request**
   - Review the changes if desired
   - Click "Merge pull request"
   - Click "Confirm merge"

### Step 2: Enable GitHub Pages

1. **Go to Repository Settings**
   - In your repository, click "Settings" (top right)

2. **Navigate to Pages Section**
   - In the left sidebar, scroll down to "Pages"
   - Click "Pages"

3. **Configure Source**
   - Under "Source", select:
     - Branch: `main` (or `master`)
     - Folder: `/ (root)`
   - Click "Save"

4. **Wait for Deployment**
   - GitHub will show: "Your site is ready to be published"
   - After 1-2 minutes, refresh the page
   - You'll see: "Your site is live at https://monksealseal.github.io/tinypets/"

### Step 3: Access Your Site

**Your public URL will be:**
```
https://monksealseal.github.io/tinypets/
```

**All resources will be accessible:**
- Main page: https://monksealseal.github.io/tinypets/
- Interactive presentation: https://monksealseal.github.io/tinypets/concord-nh-weather.html
- Analysis doc: https://monksealseal.github.io/tinypets/weather-analysis-nov4-2025
- PowerPoint guide: https://monksealseal.github.io/tinypets/POWERPOINT-CREATION-GUIDE
- Update guide: https://monksealseal.github.io/tinypets/PRESENTATION-UPDATE-GUIDE

---

## 🔄 Alternative: Use Branch Directly (Advanced)

If you prefer to keep your work on the branch and not merge to main:

1. **Go to Repository Settings → Pages**

2. **Configure Source**
   - Branch: `claude/concord-nh-weather-presentation-011CUoUZ41jzMR1u6ituKvCx`
   - Folder: `/ (root)`
   - Click "Save"

**Note:** Branch names with special characters may have issues. If you encounter problems, merge to main instead.

---

## ✅ Verification

After enabling GitHub Pages, verify everything works:

### 1. Check Main Landing Page
Visit: https://monksealseal.github.io/tinypets/
- Should see: "Weather Map Discussion - Concord, New Hampshire"
- Should see: All navigation links
- Should see: Current weather summary

### 2. Test Interactive Presentation
Click: "Launch Interactive Weather Presentation"
- Should open: concord-nh-weather.html
- Should see: Title slide
- Should work: Arrow key navigation
- Should load: Embedded weather maps (requires internet)

### 3. Check Documentation Links
Click each documentation link:
- ✅ Weather Analysis - November 4, 2025
- ✅ PowerPoint/Canva Creation Guide
- ✅ Presentation Update Guide

All should display properly formatted markdown.

### 4. Test External Links
Verify weather resource links work:
- Weather Prediction Center (WPC)
- Storm Prediction Center (SPC)
- GOES Satellite
- National Radar
- NWS Gray, Maine
- All model guidance links

---

## 🎯 Sharing Your Presentation

Once GitHub Pages is enabled, you can share:

### For Viewing Online:
**Share this link:**
```
https://monksealseal.github.io/tinypets/
```

**What others can do:**
- View the interactive presentation
- Read all documentation
- Access all guides
- Click through to weather resources
- Works on any device (mobile, tablet, desktop)

### For Presentations:
**Present directly from browser:**
1. Open: https://monksealseal.github.io/tinypets/concord-nh-weather.html
2. Press F11 for full screen
3. Use arrow keys to navigate
4. Requires internet for live maps

**Or create PowerPoint:**
1. Share: https://monksealseal.github.io/tinypets/POWERPOINT-CREATION-GUIDE
2. Others can follow guide to create their own version

---

## 🔒 Privacy & Access Control

### Public Repository (Current Setting)
- ✅ Anyone can view GitHub Pages
- ✅ Free hosting
- ✅ No login required
- ✅ Great for sharing

### Private Repository (If you need privacy)
**Note:** GitHub Pages for private repos requires GitHub Pro

If you need to make the repository private:
1. Go to Settings → General
2. Scroll to "Danger Zone"
3. Click "Change repository visibility"
4. Select "Make private"

**Warning:** This will disable GitHub Pages unless you have GitHub Pro.

---

## 🛠️ Troubleshooting

### Problem: "404 - Page Not Found"

**Solutions:**
1. **Wait:** Initial deployment takes 1-5 minutes
2. **Check branch:** Ensure GitHub Pages is set to correct branch
3. **Check URL:** Make sure using exact URL from GitHub Pages settings
4. **Refresh cache:** Try Ctrl+F5 (hard refresh)

### Problem: "Site Not Building"

**Check Actions Tab:**
1. Go to repository
2. Click "Actions" tab
3. Look for latest "pages build and deployment"
4. If failed, click to see error details

**Common fixes:**
- Ensure `_config.yml` has no syntax errors
- Ensure `index.md` has proper front matter (---  title: ... ---)
- Try re-saving GitHub Pages settings

### Problem: Interactive Presentation Shows Black Boxes

**Causes:**
1. **Internet required:** Live maps need internet connection
2. **CORS issues:** Some maps may be blocked
3. **Iframe blocking:** Some networks block iframes

**Solutions:**
- Ensure stable internet connection
- Try different browser (Chrome recommended)
- Try different network (some work networks block maps)
- Use PowerPoint version with screenshots instead

### Problem: Markdown Files Show Raw Text

**Solution:**
- Remove `.md` from URL
- GitHub Pages automatically converts
- Example: Use `/weather-analysis-nov4-2025` not `/weather-analysis-nov4-2025.md`

### Problem: Page Loads But Looks Wrong

**Solutions:**
1. **Wait for Jekyll build:** Takes 1-2 minutes
2. **Clear cache:** Ctrl+F5
3. **Try incognito mode:** Rules out cache issues
4. **Check theme:** Ensure `_config.yml` has `remote_theme: pages-themes/hacker`

---

## 📱 Mobile Optimization

Your site is responsive and works on:
- ✅ Desktop (full navigation)
- ✅ Laptop (full navigation)
- ✅ Tablet (adjusted layout)
- ✅ Phone (stacked layout)

**Test on mobile:**
1. Open URL on phone
2. Navigate to interactive presentation
3. Swipe or use on-screen buttons
4. Pinch to zoom on maps

---

## 🔄 Updating Your Site

After initial setup, any changes you push will auto-deploy:

### To Update Content:

1. **Edit files locally or on GitHub**
2. **Commit changes**
   ```bash
   git add .
   git commit -m "Update weather analysis"
   git push
   ```
3. **Wait 1-2 minutes**
4. **Refresh GitHub Pages URL**

Changes will be live automatically!

### To Update Presentation:

**For Interactive HTML:**
1. Edit `concord-nh-weather.html`
2. Commit and push
3. Changes appear in 1-2 minutes

**For Documentation:**
1. Edit `.md` files
2. Commit and push
3. Jekyll rebuilds automatically

---

## 🎓 Advanced Configuration

### Custom Domain (Optional)

If you want a custom domain like `weather.yourdomain.com`:

1. **Buy domain** (from Namecheap, Google Domains, etc.)
2. **Configure DNS:**
   - Add CNAME record
   - Point to: `monksealseal.github.io`
3. **In GitHub Pages settings:**
   - Add custom domain
   - Check "Enforce HTTPS"

### Custom Styling

To customize the look:

1. **Create `assets/css/style.scss`:**
   ```scss
   ---
   ---
   @import "{{ site.theme }}";

   // Your custom CSS here
   h1 {
     color: #0066cc;
   }
   ```

2. **Commit and push**
3. **Changes apply automatically**

### Analytics (Optional)

To track visitors:

1. **Get Google Analytics ID**
2. **Add to `_config.yml`:**
   ```yaml
   google_analytics: UA-XXXXXXXXX-X
   ```
3. **Commit and push**

---

## 📊 Usage Statistics

After enabling GitHub Pages, you can see:

**Repository Insights:**
- Go to repository
- Click "Insights"
- View traffic, clones, visitors

**GitHub Pages Stats:**
- Shows unique visitors
- Shows page views
- Updates daily

---

## ✅ Final Checklist

- [ ] Merged branch to main (or configured Pages to use branch)
- [ ] Enabled GitHub Pages in Settings
- [ ] Verified site is live (wait 1-5 minutes)
- [ ] Tested main landing page
- [ ] Tested interactive presentation
- [ ] Tested all documentation links
- [ ] Tested external weather resource links
- [ ] Verified mobile display
- [ ] Shared URL with others
- [ ] Bookmarked for easy access

---

## 🎉 You're Live!

Once setup is complete, you have:

✅ **Public website** accessible from anywhere
✅ **Interactive presentation** with live weather data
✅ **Complete documentation** online
✅ **Professional portfolio piece** to share
✅ **Mobile-friendly** responsive design
✅ **Automatic updates** with every push
✅ **Free hosting** forever (GitHub Pages)

---

## 📧 Need More Help?

**GitHub Pages Documentation:**
https://docs.github.com/en/pages

**Jekyll Documentation:**
https://jekyllrb.com/docs/

**GitHub Community:**
https://github.community/

---

**Your public weather presentation site will be:**
## https://monksealseal.github.io/tinypets/

**Share this URL with:**
- Your professor/instructor
- Classmates
- In your resume/portfolio
- On social media
- Anywhere you want to showcase your meteorology skills!

---

*Setup guide created: November 5, 2025*
*Questions? Check troubleshooting section above or GitHub Pages docs.*

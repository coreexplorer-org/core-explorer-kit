# Core Explorer Frontend - File Interaction Diagram

## Overview
This document describes the functionality and interactions between `index.html`, `profile.html`, and `project.html`.

## File Functionality

### index.html (Landing Page)
**Purpose**: Main entry point and navigation hub

**Key Features**:
- Welcome message and introduction
- Three navigation cards:
  - **Project View** → links to `project.html`
  - **Actor View** → links to `profile.html`
  - **File View** → links to `file.html` (not implemented)
- Blog posts section:
  - Fetches latest 5 posts from Atom feed (`https://blog.coreexplorer.org/feed.xml`)
  - Uses CORS proxy (`https://corsproxy.io/`)
  - Falls back to embedded feed data if fetch fails
- Search bar (UI only, not functional)
- Theme toggle (light/dark mode)
- Shared navigation bar with GitHub and email links

**External Dependencies**:
- Bootstrap 4.3.1 (CSS/JS)
- Font Awesome 5.15.4
- Bootstrap Icons 1.11.3
- jQuery 3.3.1
- Popper.js 1.14.7

---

### profile.html (Contributor Profile Page)
**Purpose**: Display individual contributor statistics and contributions

**Key Features**:
- Contributor profile display:
  - Profile picture (icon placeholder)
  - Contributor name
  - Start date of contributions
  - Repository details
- Statistics display:
  - Total Commits
  - Lines of Code
  - Files Created
- Commits over time chart:
  - Uses Chart.js for visualization
  - Shows cumulative commits from 2009-2011 (mock data)
- Top files contributed to table (static mock data)
- Search functionality:
  - Search bar accepts contributor email
  - Queries GraphQL API at `/api/graphql`
  - Default loads Satoshi's profile (`satoshin@gmx.com`)
- Theme toggle (light/dark mode)
- Shared navigation bar

**API Integration**:
- GraphQL endpoint: `/api/graphql`
- Queries:
  - `actor(email: "...")` - Get contributor name
  - `githubRepository(url: "...")` - Get repository details

**External Dependencies**:
- Same as index.html
- Chart.js 4.4.3 (for commits chart)
- XLSX.js (embedded in script tags, for file data processing)

---

### project.html (Project Overview Page)
**Purpose**: Display overall project statistics and visualizations

**Key Features**:
- Project title and description
- Project statistics (static):
  - Lines of Code: 3,214
  - Files: 4,321
  - Commits: 44,727
- Visualization placeholders:
  - Neo4j graph visualization (placeholder)
  - Heat map visualization (placeholder)
- Search bar (UI only, not functional)
- Theme toggle (light/dark mode)
- Shared navigation bar

**External Dependencies**:
- Same as index.html (no Chart.js)

---

## Interaction Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         index.html                              │
│                    (Landing Page)                               │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Navigation Cards                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │ Project View │  │ Actor View   │  │ File View    │  │  │
│  │  │              │  │              │  │ (not impl.)  │  │  │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │  │
│  │         │                  │                             │  │
│  │         │                  │                             │  │
│  └─────────┼──────────────────┼─────────────────────────────┘  │
│            │                  │                                 │
│            │                  │                                 │
│            ▼                  ▼                                 │
│  ┌─────────────────┐  ┌─────────────────┐                      │
│  │  project.html   │  │  profile.html   │                      │
│  │                 │  │                 │                      │
│  │  • Project stats│  │  • Contributor  │                      │
│  │  • Placeholders │  │    search       │                      │
│  │  • No API calls │  │  • GraphQL API  │                      │
│  │                 │  │    /api/graphql │                      │
│  │                 │  │  • Chart.js     │                      │
│  │                 │  │    visualization │                      │
│  └─────────────────┘  └─────────────────┘                      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Blog Posts Section                                       │  │
│  │  • Fetches from: blog.coreexplorer.org/feed.xml          │  │
│  │  • Via CORS proxy: corsproxy.io                          │  │
│  │  • Fallback: embedded Atom feed data                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Shared Features (All Pages)                             │  │
│  │  • Theme toggle (light/dark mode)                        │  │
│  │  • Navigation bar with logo                                │  │
│  │  • GitHub & email links                                   │  │
│  │  • Responsive design (mobile/tablet/desktop)             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

                    ┌──────────────────┐
                    │  External APIs    │
                    │                  │
                    │  • GraphQL API   │
                    │    /api/graphql  │
                    │                  │
                    │  • Blog Feed     │
                    │    blog.core...  │
                    │                  │
                    │  • CORS Proxy    │
                    │    corsproxy.io  │
                    └──────────────────┘
```

## Navigation Flow

```
User Journey:
1. User lands on index.html
   ↓
2. User clicks "Project View" card
   → Navigates to project.html
   → Views project statistics and placeholders
   ↓
3. User clicks navbar logo/brand (or back button)
   → Returns to index.html
   ↓
4. User clicks "Actor View" card
   → Navigates to profile.html
   → Views default profile (Satoshi)
   ↓
5. User enters email in search bar
   → Submits GraphQL query
   → Updates profile with contributor data
   → Chart updates (currently uses mock data)
```

## Shared Components

All three pages share:
1. **Navigation Bar**:
   - Core Explorer logo
   - GitHub link
   - Email link (placeholder)
   - Theme toggle button
   - Search bar (functionality varies)

2. **Footer**:
   - Same links as navbar
   - Theme toggle button

3. **Styling**:
   - CSS variables for theming
   - Bootstrap 4.3.1 framework
   - Responsive breakpoints
   - Dark/light mode support

4. **Theme System**:
   - CSS custom properties (`--bs-body-bg`, `--bs-primary`, etc.)
   - Toggle between light and dark modes
   - Persists during page navigation (via body class)

## Data Flow

### profile.html Data Flow:
```
User Input (Email)
    ↓
searchContributor()
    ↓
fetchContributorData(email)
    ↓
sendQuery(GraphQL query)
    ↓
POST /api/graphql
    ↓
Response: { actor: { name }, repository: {...} }
    ↓
Update DOM elements
    ↓
Render commits chart (mock data)
```

### index.html Data Flow:
```
Page Load
    ↓
fetchBlogPosts()
    ↓
Fetch: corsproxy.io/?blog.coreexplorer.org/feed.xml
    ↓
Parse Atom XML
    ↓
Extract latest 5 entries
    ↓
Render blog post cards
    ↓
(On error: use fallback embedded feed)
```

## Current Limitations

1. **project.html**:
   - No API integration
   - Static statistics
   - Visualization placeholders not implemented

2. **profile.html**:
   - Chart uses mock data (not from API)
   - Top files table is static
   - Statistics are hardcoded

3. **index.html**:
   - Search bar not functional
   - File View card links to non-existent page

4. **Navigation**:
   - Navbar brand links use `#` (should link to index.html)
   - No breadcrumb navigation

## API Endpoints Used

- `POST /api/graphql` - GraphQL endpoint for contributor and repository data
- `GET https://blog.coreexplorer.org/feed.xml` - Atom feed for blog posts (via proxy)


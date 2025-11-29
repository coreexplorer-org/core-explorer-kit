# Core Explorer Frontend - Interaction Diagram

## Visual Flow Diagram

```mermaid
graph TB
    Start([User]) --> Index[index.html<br/>Landing Page]
    
    Index --> |Click Project View Card| Project[project.html<br/>Project Overview]
    Index --> |Click Actor View Card| Profile[profile.html<br/>Contributor Profile]
    Index --> |Click File View Card| FileView[file.html<br/>Not Implemented]
    
    Index --> |Fetches Blog Posts| BlogAPI[Blog Feed API<br/>blog.coreexplorer.org]
    BlogAPI --> |Via CORS Proxy| Index
    
    Profile --> |User Searches Email| GraphQL[GraphQL API<br/>/api/graphql]
    GraphQL --> |Returns Data| Profile
    Profile --> |Renders Chart| ChartJS[Chart.js<br/>Visualization]
    
    Project --> |Static Data| ProjectStats[Project Statistics<br/>Hardcoded Values]
    
    Index -.-> |Navbar Logo| Index
    Profile -.-> |Navbar Logo| Index
    Project -.-> |Navbar Logo| Index
    
    style Index fill:#f7931a,stroke:#333,stroke-width:3px,color:#fff
    style Profile fill:#2d2d2d,stroke:#f7931a,stroke-width:2px,color:#f7931a
    style Project fill:#2d2d2d,stroke:#f7931a,stroke-width:2px,color:#f7931a
    style GraphQL fill:#007bff,stroke:#333,stroke-width:2px,color:#fff
    style BlogAPI fill:#007bff,stroke:#333,stroke-width:2px,color:#fff
    style FileView fill:#999,stroke:#333,stroke-width:1px,color:#fff
```

## Component Interaction Diagram

```mermaid
graph LR
    subgraph "index.html"
        A1[Navbar]
        A2[View Cards]
        A3[Blog Posts]
        A4[Theme Toggle]
        A1 --> A2
        A2 --> A3
        A1 --> A4
    end
    
    subgraph "profile.html"
        B1[Navbar]
        B2[Profile Section]
        B3[Stats Display]
        B4[Commits Chart]
        B5[Files Table]
        B6[Search Bar]
        B1 --> B2
        B2 --> B3
        B3 --> B4
        B3 --> B5
        B6 --> B2
        B1 --> B4
    end
    
    subgraph "project.html"
        C1[Navbar]
        C2[Project Stats]
        C3[Graph Placeholder]
        C4[Heatmap Placeholder]
        C1 --> C2
        C2 --> C3
        C2 --> C4
    end
    
    A2 -->|Navigate| B1
    A2 -->|Navigate| C1
    B1 -.->|Return| A1
    C1 -.->|Return| A1
```

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant Index as index.html
    participant Profile as profile.html
    participant API as GraphQL API
    participant Blog as Blog Feed
    
    User->>Index: Load page
    Index->>Blog: Fetch blog posts
    Blog-->>Index: Return Atom feed
    Index-->>User: Display blog posts
    
    User->>Index: Click "Actor View"
    Index->>Profile: Navigate to profile.html
    Profile->>API: Query contributor (default: Satoshi)
    API-->>Profile: Return contributor data
    Profile-->>User: Display profile
    
    User->>Profile: Enter email & search
    Profile->>API: GraphQL query (actor + repository)
    API-->>Profile: Return data
    Profile-->>User: Update profile display
```

## Feature Matrix

| Feature | index.html | profile.html | project.html |
|---------|-----------|--------------|--------------|
| Navigation Bar | ✅ | ✅ | ✅ |
| Theme Toggle | ✅ | ✅ | ✅ |
| Search Bar | ⚠️ (UI only) | ✅ (Functional) | ⚠️ (UI only) |
| API Integration | ✅ (Blog feed) | ✅ (GraphQL) | ❌ |
| Data Visualization | ❌ | ✅ (Chart.js) | ⚠️ (Placeholders) |
| Responsive Design | ✅ | ✅ | ✅ |
| External Links | ✅ (GitHub, Email) | ✅ (GitHub, Email) | ✅ (GitHub, Email) |

**Legend:**
- ✅ Fully implemented
- ⚠️ Partially implemented
- ❌ Not implemented

## Key Interactions Summary

1. **Navigation**: 
   - `index.html` serves as the hub with navigation cards
   - Both `profile.html` and `project.html` can return via navbar logo
   - Direct URL access to any page is supported

2. **Data Fetching**:
   - `index.html`: Fetches blog posts on page load
   - `profile.html`: Fetches contributor data on search or page load (default)
   - `project.html`: No data fetching (static content)

3. **Shared State**:
   - Theme preference is not persisted (resets on navigation)
   - All pages share the same CSS variables and styling
   - Navigation structure is consistent across all pages

4. **User Interactions**:
   - Theme toggle: Works on all pages independently
   - Search: Only functional on `profile.html`
   - Navigation: Card clicks and navbar logo clicks


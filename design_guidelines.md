{
  "design_system_name": "Sprout ATS (Greenhouse-inspired, internal SaaS)",
  "brand_attributes": [
    "fast + scannable (power-user friendly)",
    "calm, minimal, professional",
    "trustworthy + operational",
    "green accent as navigation + primary actions (not as semantic success)"
  ],
  "inspiration_refs": {
    "notes": "Use Greenhouse-like restraint + progressive disclosure. Dense tables + kanban with clear stage headers. Avoid bloat; keep actions close to context.",
    "urls": [
      {
        "title": "ATS scheduling flow case study (layout ideas for scheduler + right panel)",
        "url": "https://medium.com/design-bootcamp/designing-a-candidate-scheduling-management-flow-for-an-applicant-tracking-system-ats-c6ecf27e75fc"
      },
      {
        "title": "ATS dashboard UI shot (Dribbble reference for cards + pipeline)",
        "url": "https://dribbble.com/shots/27161242-Applicant-Tracking-System-Dashboard-UI-Design"
      },
      {
        "title": "Kanban recruitment pipeline patterns", 
        "url": "https://treegarden.io/blog/kanban-recruitment-pipeline/"
      },
      {
        "title": "shadcn/ui Table (baseline patterns)",
        "url": "https://www.shadcn.io/ui/table"
      }
    ]
  },
  "typography": {
    "font_pairing": {
      "display_and_headings": {
        "name": "Space Grotesk",
        "weights": [500, 600, 700],
        "usage": "App shell titles, page headings, KPI numbers, stage headers"
      },
      "body_ui": {
        "name": "Work Sans",
        "weights": [400, 500, 600],
        "usage": "Tables, forms, helper text, long notes"
      },
      "mono": {
        "name": "IBM Plex Mono",
        "weights": [400, 500],
        "usage": "IDs, timestamps, audit log, CSV preview"
      }
    },
    "implementation": {
      "google_fonts": [
        "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Work+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap"
      ],
      "css_vars": {
        "--font-sans": "Work Sans, ui-sans-serif, system-ui",
        "--font-display": "Space Grotesk, ui-sans-serif, system-ui",
        "--font-mono": "IBM Plex Mono, ui-monospace, SFMono-Regular"
      }
    },
    "type_scale_tailwind": {
      "h1": "text-4xl sm:text-5xl lg:text-6xl font-[650] tracking-[-0.02em]",
      "h2": "text-base md:text-lg font-medium text-muted-foreground",
      "section_title": "text-sm font-semibold tracking-[-0.01em]",
      "body": "text-sm md:text-base",
      "small": "text-xs text-muted-foreground",
      "kpi_number": "text-2xl md:text-3xl font-semibold tabular-nums"
    }
  },
  "color_system": {
    "strategy": [
      "Light mode default (internal tool). Dark mode optional later.",
      "Brand green is for navigation/primary actions only.",
      "Semantic success uses a different green family (more muted) to avoid confusion.",
      "No transparent backgrounds behind text; cards are solid."
    ],
    "tokens_hsl_for_shadcn": {
      "notes": "Update /frontend/src/index.css :root tokens to these values (HSL). Keep contrast AA.",
      "light": {
        "--background": "210 20% 98%",
        "--foreground": "222 47% 11%",
        "--card": "0 0% 100%",
        "--card-foreground": "222 47% 11%",
        "--popover": "0 0% 100%",
        "--popover-foreground": "222 47% 11%",
        "--primary": "158 64% 34%",
        "--primary-foreground": "0 0% 100%",
        "--secondary": "210 16% 94%",
        "--secondary-foreground": "222 47% 11%",
        "--muted": "210 16% 94%",
        "--muted-foreground": "215 16% 40%",
        "--accent": "156 35% 92%",
        "--accent-foreground": "166 72% 18%",
        "--destructive": "0 72% 51%",
        "--destructive-foreground": "0 0% 100%",
        "--border": "214 18% 88%",
        "--input": "214 18% 88%",
        "--ring": "158 64% 34%",
        "--radius": "0.75rem",
        "--chart-1": "158 64% 34%",
        "--chart-2": "199 78% 40%",
        "--chart-3": "43 96% 56%",
        "--chart-4": "262 52% 55%",
        "--chart-5": "0 72% 51%"
      },
      "dark_optional": {
        "--background": "222 47% 7%",
        "--foreground": "210 40% 98%",
        "--card": "222 47% 9%",
        "--card-foreground": "210 40% 98%",
        "--popover": "222 47% 9%",
        "--popover-foreground": "210 40% 98%",
        "--primary": "158 64% 45%",
        "--primary-foreground": "222 47% 11%",
        "--secondary": "217 19% 16%",
        "--secondary-foreground": "210 40% 98%",
        "--muted": "217 19% 16%",
        "--muted-foreground": "215 20% 65%",
        "--accent": "158 30% 18%",
        "--accent-foreground": "156 35% 92%",
        "--destructive": "0 62% 35%",
        "--destructive-foreground": "210 40% 98%",
        "--border": "217 19% 16%",
        "--input": "217 19% 16%",
        "--ring": "158 64% 45%"
      }
    },
    "hex_palette_reference": {
      "bg": "#F7FAFC",
      "surface": "#FFFFFF",
      "text": "#0F172A",
      "muted_text": "#475569",
      "border": "#E2E8F0",
      "brand_green": "#0F9D6A",
      "brand_green_hover": "#0B8157",
      "brand_green_soft": "#DDF5EA",
      "info_blue": "#0EA5E9",
      "warning_amber": "#F59E0B",
      "danger_red": "#EF4444",
      "semantic_success_alt": "#16A34A"
    },
    "gradients_and_texture": {
      "rules": "Gradients only as decorative section background accents (<=20% viewport). Never on text-heavy areas or small UI elements.",
      "allowed_gradients": [
        {
          "name": "hero-wash",
          "css": "radial-gradient(900px circle at 12% 8%, rgba(15,157,106,0.14), transparent 55%), radial-gradient(700px circle at 88% 18%, rgba(14,165,233,0.10), transparent 52%)"
        }
      ],
      "noise_overlay_css": "background-image: url('https://images.unsplash.com/photo-1708305729900-906f34a7d49d?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85'); background-size: cover; background-position: center; opacity: 0.06; mix-blend-mode: multiply;",
      "note": "Prefer CSS noise via pseudo-element if possible; if using image, keep opacity <= 0.06 and never behind text blocks."
    }
  },
  "layout_and_grid": {
    "app_shell": {
      "pattern": "Desktop-first 3-zone: left sidebar (nav) + topbar (global actions) + content area. Optional right inspector drawer for candidate details.",
      "sidebar": {
        "width": "w-[264px] (desktop), collapsible to icons-only w-[72px]",
        "behavior": "Sticky, scrollable nav; role-aware items. Active item uses brand green left border + subtle background.",
        "tailwind": "bg-card border-r border-border"
      },
      "topbar": {
        "height": "h-14",
        "contents": "Global search (Command), notifications bell, quick-add candidate, user menu",
        "tailwind": "bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80 border-b border-border"
      },
      "content_grid": {
        "max_width": "max-w-[1440px]",
        "padding": "px-4 sm:px-6 lg:px-8 py-6",
        "density": "Use compact spacing in tables; generous spacing between sections (gap-6 to gap-8)."
      }
    },
    "page_templates": {
      "dashboard": "KPI row (4-6 cards) -> pipeline snapshot (chart) -> 2-column: My Tasks + Recent Activity",
      "candidates": "Header with filters + view toggle (Table/Kanban) -> main area; right side optional details drawer",
      "candidate_profile": "Two-column: left (resume preview + timeline) right (notes + tags + actions). On mobile: stacked with sticky action bar.",
      "interviews": "Calendar week/day + right list of upcoming interviews; schedule dialog from CTA.",
      "admin": "Tabs layout with dense tables; audit log uses mono + filters"
    }
  },
  "components": {
    "component_path": {
      "shadcn_primary": "/app/frontend/src/components/ui",
      "use_components": [
        "button.jsx",
        "input.jsx",
        "label.jsx",
        "badge.jsx",
        "card.jsx",
        "table.jsx",
        "tabs.jsx",
        "dialog.jsx",
        "drawer.jsx",
        "sheet.jsx",
        "dropdown-menu.jsx",
        "command.jsx",
        "calendar.jsx",
        "popover.jsx",
        "tooltip.jsx",
        "separator.jsx",
        "scroll-area.jsx",
        "checkbox.jsx",
        "switch.jsx",
        "textarea.jsx",
        "sonner.jsx"
      ]
    },
    "navigation": {
      "sidebar_item": {
        "states": {
          "default": "text-muted-foreground hover:text-foreground hover:bg-secondary",
          "active": "text-foreground bg-accent border-l-2 border-l-[hsl(var(--primary))]",
          "focus": "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        },
        "data_testid_examples": [
          "data-testid=\"sidebar-nav-dashboard\"",
          "data-testid=\"sidebar-nav-candidates\"",
          "data-testid=\"sidebar-nav-interviews\"",
          "data-testid=\"sidebar-nav-admin\""
        ]
      },
      "top_search": {
        "component": "Command",
        "pattern": "Cmd+K opens global search for candidates, roles, actions",
        "data_testid": "global-command-search"
      }
    },
    "dashboard_widgets": {
      "kpi_card": {
        "component": "Card",
        "layout": "Title (text-xs uppercase tracking) + number (tabular) + delta badge",
        "tailwind": "rounded-xl border border-border bg-card shadow-[0_1px_0_rgba(15,23,42,0.04)]",
        "data_testid": "dashboard-kpi-card"
      },
      "pipeline_snapshot": {
        "library": "recharts",
        "chart_types": ["funnel-like horizontal bar", "stacked bar by stage"],
        "styling": "Use muted stage colors with one brand-green highlight for selected stage. Avoid gradients.",
        "data_testid": "dashboard-pipeline-snapshot"
      },
      "activity_feed": {
        "pattern": "Compact list with avatar initials + action + timestamp (mono)",
        "data_testid": "dashboard-activity-feed"
      },
      "my_tasks": {
        "pattern": "Checkbox list with due date chips; quick filters (Today/This week/Overdue)",
        "data_testid": "dashboard-my-tasks"
      }
    },
    "candidates_table": {
      "component": "Table",
      "density": {
        "row": "h-10 (default), optional compact h-8",
        "cell": "py-2 (default), compact py-1",
        "font": "text-sm",
        "sticky_header": "sticky top-0 bg-card z-10"
      },
      "must_have_columns": [
        "Candidate (name + email)",
        "Role",
        "Stage",
        "Owner",
        "Last activity",
        "Next interview",
        "Score"
      ],
      "filters": {
        "components": ["Input", "Select", "Popover"],
        "pattern": "Filter bar with chips; show active filters as removable badges",
        "data_testid_examples": [
          "candidates-search-input",
          "candidates-filter-stage-select",
          "candidates-filter-owner-select",
          "candidates-bulk-actions-button",
          "candidates-export-csv-button"
        ]
      },
      "performance": {
        "virtualization": "Use react-virtual (or TanStack Virtual) for thousands of rows; keep row height fixed.",
        "avoid": "Avoid heavy shadows per row; use border separators only."
      }
    },
    "kanban": {
      "library": "@dnd-kit/core + @dnd-kit/sortable",
      "layout": "Horizontal scroll columns; each column fixed width 280-320px; sticky stage header.",
      "column_style": "bg-secondary rounded-xl p-3 border border-border",
      "card_style": "bg-card rounded-lg border border-border p-3 hover:shadow-sm",
      "micro_interactions": [
        "On drag start: card scales to 1.02 + shadow",
        "Drop target column: subtle accent ring",
        "Stage header shows count + SLA color dot (time-in-stage)"
      ],
      "data_testid_examples": [
        "kanban-stage-applied",
        "kanban-stage-interview",
        "kanban-candidate-card-<id>",
        "kanban-view-toggle"
      ]
    },
    "candidate_profile": {
      "resume_preview": {
        "pattern": "Left panel uses AspectRatio + ScrollArea; PDF iframe fallback to download link",
        "data_testid": "candidate-resume-preview"
      },
      "timeline": {
        "pattern": "Vertical timeline list (no heavy graphics). Use small dots + left border.",
        "data_testid": "candidate-activity-timeline"
      },
      "notes": {
        "component": "Textarea",
        "pattern": "Notes composer pinned above notes list; mentions optional later",
        "data_testid": "candidate-notes"
      }
    },
    "resume_parsing_review": {
      "pattern": "Upload -> parsing state -> review form with confidence flags.",
      "confidence_ui": {
        "high": "no badge",
        "medium": "Badge variant=secondary label 'Review'",
        "low": "Badge variant=destructive label 'Low confidence' + field highlight ring"
      },
      "form_components": ["Form", "Input", "Select", "Textarea", "Checkbox"],
      "data_testid_examples": [
        "resume-upload-dropzone",
        "resume-upload-browse-button",
        "parsed-review-save-button",
        "parsed-review-field-full-name",
        "parsed-review-field-email"
      ]
    },
    "interviews_calendar": {
      "component": "Calendar",
      "views": ["day", "week"],
      "pattern": "Week view as grid; day view as agenda list on mobile.",
      "schedule_dialog": {
        "component": "Dialog",
        "fields": ["candidate", "interviewers", "date", "time", "location/video", "timezone"],
        "data_testid": "schedule-interview-dialog"
      },
      "data_testid_examples": [
        "interviews-calendar",
        "interviews-view-toggle-week",
        "interviews-view-toggle-day",
        "schedule-interview-button"
      ]
    },
    "scorecard": {
      "component": "Dialog or Drawer (mobile)",
      "rating": "Use RadioGroup or Slider per attribute; keep 4-6 attributes max.",
      "data_testid": "scorecard-submit"
    },
    "admin_panel": {
      "layout": "Tabs: Users | Pipeline Stages | Departments & Tags | Audit Log",
      "users": "Dense table + invite user dialog",
      "audit_log": "Table with mono timestamps + filters; export CSV",
      "data_testid_examples": [
        "admin-tabs",
        "admin-users-table",
        "admin-invite-user-button",
        "admin-audit-log-table"
      ]
    },
    "notifications": {
      "component": "DropdownMenu",
      "pattern": "Bell icon with unread dot; dropdown list with 'Mark all read'",
      "data_testid": "notifications-menu"
    },
    "toasts": {
      "library": "sonner",
      "component": "Sonner (from /app/frontend/src/components/ui/sonner.jsx)",
      "usage": "Use for save confirmations, CSV export started, parsing complete",
      "data_testid": "toast-region"
    }
  },
  "motion_and_microinteractions": {
    "library": "framer-motion (recommended)",
    "install": "npm i framer-motion",
    "principles": [
      "Fast UI: 120–180ms for hover/focus, 180–240ms for dialogs/drawers",
      "Use transform-based animations (translate/scale) for performance",
      "Respect prefers-reduced-motion"
    ],
    "patterns": {
      "button": "hover: translateY(-1px) + shadow-sm; active: scale-[0.98]",
      "cards": "hover: shadow-sm (not heavy) + border color shift",
      "kanban_drag": "drag overlay scale 1.02 + shadow-md",
      "page_enter": "subtle fade + y: 6px"
    },
    "tailwind_transition_rules": {
      "allowed": ["transition-colors", "transition-opacity", "transition-shadow"],
      "forbidden": "transition-all"
    }
  },
  "accessibility": {
    "requirements": [
      "WCAG AA contrast for text and interactive elements",
      "Visible focus ring using ring token",
      "Keyboard navigable sidebar, tables, dialogs",
      "Use aria-label for icon-only buttons",
      "Respect prefers-reduced-motion"
    ],
    "table_a11y": "Ensure row selection uses Checkbox with label/aria; bulk actions announce count.",
    "color_a11y": "Do not rely on color alone for stage status; pair with label/badge."
  },
  "data_density_rules": {
    "do": [
      "Use tabular-nums for metrics",
      "Use badges for stage/status",
      "Use sticky headers for tables",
      "Use progressive disclosure: details in drawer/side panel"
    ],
    "dont": [
      "No heavy shadows everywhere",
      "No large hero sections",
      "No decorative gradients in reading areas",
      "No transparent text backgrounds"
    ]
  },
  "image_urls": {
    "login_side_image_optional": [
      {
        "url": "https://images.unsplash.com/photo-1588091210060-1ee4fab270ae?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2ODl8MHwxfHNlYXJjaHwxfHxtb2Rlcm4lMjBvZmZpY2UlMjBoaXJpbmclMjB0ZWFtJTIwbWVldGluZyUyMG1pbmltYWx8ZW58MHx8fGdyZWVufDE3ODQxMjE1NDh8MA&ixlib=rb-4.1.0&q=85",
        "category": "login",
        "description": "Subtle office/hiring context image for login split layout (desktop only). Apply grayscale + low opacity overlay; never behind text."
      }
    ],
    "texture_optional": [
      {
        "url": "https://images.unsplash.com/photo-1708305729900-906f34a7d49d?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85",
        "category": "background-texture",
        "description": "Very subtle grain/blur texture for page background pseudo-element (opacity <= 0.06)."
      }
    ]
  },
  "instructions_to_main_agent": {
    "global": [
      "Remove CRA default App.css centering/dark header styles; rely on Tailwind + tokens.",
      "Update /frontend/src/index.css :root tokens to the provided HSL values to get Greenhouse-like green accent.",
      "Add Google Fonts import in index.html (or CSS import) and set Tailwind font families (or CSS vars) to use Space Grotesk + Work Sans.",
      "Ensure every interactive element and key info element includes data-testid (kebab-case).",
      "Use shadcn components from /frontend/src/components/ui (JS files). Do not use raw HTML dropdown/calendar/toast.",
      "For candidates table with thousands of rows: implement virtualization (TanStack Virtual) and keep row height fixed.",
      "Implement Kanban with @dnd-kit; keep columns horizontally scrollable with sticky headers.",
      "Use Sonner for toasts; avoid custom toast implementations."
    ],
    "page_specific": {
      "login": [
        "Split layout on desktop: left login card, right muted image panel. On mobile: single column.",
        "Include demo account quick-select as segmented buttons (Recruiter/Interviewer/Admin) with data-testid."
      ],
      "dashboard": [
        "KPI cards first row; pipeline snapshot chart second; tasks + activity in two-column grid.",
        "Keep charts minimal; prefer bars over complex visuals."
      ],
      "candidates": [
        "Provide Table/Kanban toggle; persist preference.",
        "Bulk actions appear only when rows selected (progressive disclosure)."
      ],
      "candidate_profile": [
        "Use right-side drawer for quick edits (stage, owner, tags) to avoid navigation churn.",
        "Resume preview must have download fallback."
      ],
      "interviews": [
        "Week/day toggle; on mobile default to agenda list.",
        "Schedule dialog uses Calendar + time select; show timezone selector."
      ],
      "admin": [
        "Tabs with dense tables; dialogs for create/edit.",
        "Audit log uses mono timestamps and filter chips."
      ]
    },
    "recommended_libs": [
      {
        "name": "@dnd-kit/core",
        "install": "npm i @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities",
        "usage": "Kanban drag-and-drop stage moves"
      },
      {
        "name": "recharts",
        "install": "npm i recharts",
        "usage": "Pipeline snapshot + dashboard charts"
      },
      {
        "name": "@tanstack/react-virtual",
        "install": "npm i @tanstack/react-virtual",
        "usage": "Virtualized candidate table for performance"
      },
      {
        "name": "framer-motion",
        "install": "npm i framer-motion",
        "usage": "Micro-interactions + dialog/drawer transitions"
      }
    ],
    "tailwind_snippets": {
      "primary_button": "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] hover:bg-emerald-700 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      "secondary_button": "bg-secondary text-secondary-foreground hover:bg-secondary/80",
      "ghost_button": "hover:bg-secondary text-foreground",
      "input": "h-10 rounded-lg bg-card",
      "badge_stage": "rounded-full px-2.5 py-0.5 text-xs"
    }
  },
  "GRADIENT_RESTRICTION_RULE": {
    "prohibited": [
      "blue-500 to purple-600",
      "purple-500 to pink-500",
      "green-500 to blue-500",
      "red to pink"
    ],
    "never": [
      "Let gradients cover more than 20% of the viewport",
      "Apply gradients to text-heavy content or reading areas",
      "Use gradients on small UI elements (<100px width)",
      "Stack multiple gradient layers in the same viewport"
    ],
    "enforcement": "If gradient area exceeds 20% of viewport OR affects readability, then use solid colors."
  },
  "GENERAL_UI_UX_DESIGN_GUIDELINES": [
    "You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms",
    "You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text",
    "NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json",
    "\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc\n",
    "\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead.\n   ",
    "\n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n",
    "\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   ",
    "\n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n",
    "\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n",
    "\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n",
    "\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n",
    "\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n",
    "\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n",
    "\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n"
  ]
}

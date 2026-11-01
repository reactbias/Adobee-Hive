// Postings to start from on the hiring screen. They are data, not interface text: a posting is whatever a company
// pastes, so these are written the way a company would, and stay in English whichever language the page is in.

export type Sample = { id: string; title: string; text: string };

export const SAMPLES: Sample[] = [
  {
    id: "software",
    title: "Senior Software Engineer (Cloud & Backend)",
    text: `Senior Software Engineer (Cloud & Backend)

We are looking for a Senior Software Engineer to design and run cloud-based backend services.

Requirements:
- 5+ years of professional software engineering experience
- Strong Python; experience with microservices and REST APIs
- Hands-on cloud experience (AWS, Azure or GCP), containers (Docker/Kubernetes), CI/CD
- Experience with SQL/NoSQL databases and data pipelines
- Nice to have: Terraform / infrastructure as code, mentoring junior engineers
`,
  },
  {
    id: "marketing",
    title: "Marketing Manager (B2B)",
    text: `Marketing Manager (B2B)

We are looking for a Marketing Manager to lead our B2B marketing in the DACH region.

Requirements:
- 4+ years of experience in B2B or brand marketing
- Experience planning and managing campaign budgets
- SEO / content marketing and analytics tools (Google Analytics, HubSpot or similar)
- Team leadership experience is a plus
- Fluent German and English
`,
  },
  {
    id: "devops",
    title: "DevOps Engineer",
    text: `DevOps Engineer

Requirements:
- Kubernetes and Docker in production
- Terraform or other infrastructure as code
- CI/CD pipelines
- Python scripting

Nice to have:
- Cloud certification (AWS or GCP)
`,
  },
];

"""Example cards for real businesses, compiled by Team B6 from their public websites for the "Ask the Hive" demo.

These are not the businesses' own cards. Each one carries a `provenance` block (source, date read, not verified by
the owner), so the card's trust block reports it as unclaimed and every answer says so. The Hive signs them as the
compiler, which proves only that nobody changed them after we did; it says nothing about the owner.

Rules for this file: public company information only, no people, no contact details, no logos, no prices or dates we
could not read on the business's own site. Anything we could not confirm is marked as such. The fictional Basel
businesses stay in `hive_seed.py`.
"""

READ_ON = "2026-10-31"
NOTE = (
    "Unofficial demo card compiled by Team B6 from public information. Not endorsed by or verified with the business."
)


def _provenance(url: str) -> dict[str, object]:
    return {"source": "public website", "url": url, "read_on": READ_ON, "verified_by_owner": False, "note": NOTE}


# Item tags drive the mood preference in explore.py: learning, calm, short, long, practical, special, social,
# outdoor, news. Items with `action` can be handed off to the business's own site, after the person says yes.
CARDS = [
    {
        "id": "x-bekenya",
        "slug": "bekenya",
        "kind": "adventure",
        "name": "BeKenya",
        "aliases": ["bekenya", "be kenya", "kenya", "safari"],
        "tagline": "Expert-guided safaris and coastal trips in Kenya",
        "description": "Small tour operator for Kenya: safaris, the Swahili coast, culture walks and a Mount Kenya "
        "trek. A share of each trip goes to community programmes in the places visited.",
        "website": "https://bekenya.com",
        "location": "Kenya (trips operated from Watamu); planning office in Switzerland",
        "features": ["safari", "beach", "culture", "hiking", "guided", "community programmes"],
        "offers": [
            {
                "id": "kenya-21",
                "title": "21 days Kenya: safari, culture and coast",
                "summary": "Maasai Mara, Nakuru and Naivasha, then Mombasa and Fort Jesus, Watamu, Tsavo East.",
                "duration": "21 days",
                "price": {
                    "amount": 1350,
                    "currency": "EUR",
                    "per": "person",
                    "note": "Jan to Jun; EUR 1,620 Jul to Dec; tours only, hotels extra",
                },
                "tags": ["long", "special", "outdoor", "learning"],
                "action": "Plan this trip",
            },
            {
                "id": "mara",
                "title": "Maasai Mara safari",
                "summary": "Big Five and the Great Migration with expert guides. Safaris run from two days to a week.",
                "duration": "2 to 7 days",
                "price": None,
                "tags": ["outdoor", "special", "short"],
                "action": "Plan your safari",
            },
            {
                "id": "watamu",
                "title": "Watamu beach and marine park",
                "summary": "White sand, coral reefs and the Indian Ocean; deep-sea fishing on request.",
                "duration": "flexible",
                "price": None,
                "tags": ["calm", "outdoor", "special"],
                "action": "Plan this trip",
            },
            {
                "id": "mombasa",
                "title": "Mombasa Old Town and Fort Jesus walk",
                "summary": "Walking tour of the Old Town with a heritage guide.",
                "duration": "half a day",
                "price": None,
                "tags": ["learning", "short", "calm"],
                "action": "Talk to us",
            },
            {
                "id": "mount-kenya",
                "title": "Mount Kenya trek",
                "summary": "Four days, up the Sirimon route and down via Naro Moru.",
                "duration": "4 days",
                "price": None,
                "tags": ["outdoor", "long", "social"],
                "action": "Plan this trip",
            },
        ],
        "events": [],
        "policies": {"booking": "Concierge form with dates and budget; payment terms are not published"},
        "provenance": _provenance("https://bekenya.com"),
    },
    {
        "id": "x-4xor",
        "slug": "4xor",
        "kind": "service",
        "name": "4XOR",
        "aliases": ["4xor", "4 xor"],
        "tagline": "Software studio for AI workflows",
        "description": "Small Swiss software studio that builds AI-assisted workflows and web products for "
        "businesses. The offers below illustrate the kind of work; the studio's own list is on its website.",
        "website": "https://4xor.com",
        "location": "Switzerland",
        "features": ["ai workflows", "software", "automation", "web"],
        "offers": [
            {
                "id": "workflow-scan",
                "title": "Workflow scan (illustrative)",
                "summary": "One conversation to find the repeated office task worth automating first.",
                "duration": "1 hour",
                "price": None,
                "tags": ["short", "calm", "practical"],
                "action": "Ask for a call",
            },
            {
                "id": "workflow-build",
                "title": "AI workflow build (illustrative)",
                "summary": "Turns one repeated task into an AI-assisted flow where a person approves each step.",
                "duration": "a few weeks",
                "price": None,
                "tags": ["practical", "long", "learning"],
                "action": "Ask for a quote",
            },
        ],
        "events": [],
        "policies": {"engagement": "By request through the website"},
        "provenance": _provenance("https://4xor.com"),
    },
    {
        "id": "x-endress",
        "slug": "endress-hauser",
        "kind": "industrial",
        "name": "Endress+Hauser",
        "aliases": ["endress", "hauser", "e+h", "endress+hauser"],
        "tagline": "Measurement instruments, services and digital solutions for process automation",
        "description": "Family-owned process automation group headquartered in Reinach near Basel. Instruments for "
        "flow, level, pressure, temperature and liquid, gas and optical analysis, with commissioning, calibration "
        "and repair services and the Netilion IIoT suite. Serves food and beverage, water and wastewater, chemicals, "
        "life sciences, oil and gas, energy, mining and metals.",
        "website": "https://www.endress.com",
        "location": "Reinach BL, Switzerland (headquarters); sales and service worldwide",
        "features": ["flow", "level", "pressure", "temperature", "liquid analysis", "calibration", "iiot"],
        "offers": [
            {
                "id": "flow",
                "title": "Flow measurement",
                "summary": "Electromagnetic, Coriolis, ultrasonic, vortex, thermal mass and differential pressure "
                "flowmeters. Sizing and spec lookup with the Applicator and Product finder tools.",
                "duration": None,
                "price": None,
                "tags": ["practical", "learning"],
                "action": "Product finder",
            },
            {
                "id": "level",
                "title": "Level measurement",
                "summary": "Radar, guided radar, ultrasonic, capacitance, hydrostatic and vibronic point level.",
                "duration": None,
                "price": None,
                "tags": ["practical"],
                "action": "Product finder",
            },
            {
                "id": "analysis",
                "title": "Liquid, gas and optical analysis",
                "summary": "pH, conductivity, turbidity, chlorine, oxygen, TOC and nutrients with Memosens sensors; "
                "TDLAS, Raman and emission monitoring for gases.",
                "duration": None,
                "price": None,
                "tags": ["practical", "learning"],
                "action": "Product finder",
            },
            {
                "id": "calibration",
                "title": "Calibration and maintenance service",
                "summary": "On-site calibration, verification, preventive maintenance and instrument repair; "
                "calibration interval optimisation for an installed base.",
                "duration": None,
                "price": None,
                "tags": ["practical", "calm"],
                "action": "Request service",
            },
            {
                "id": "netilion",
                "title": "Netilion and the customer portal",
                "summary": "IIoT suite for device health, analytics and a digital twin library; spare parts finder "
                "and device viewer by serial number.",
                "duration": None,
                "price": None,
                "tags": ["practical", "learning"],
                "action": "Open the portal",
            },
        ],
        "events": [
            {
                "id": "modbus-2026-11",
                "date": "2026-11-30",
                "title": "Certified Basic Modbus Technology course",
                "tags": ["learning", "practical"],
                "action": "Register",
            },
            {
                "id": "hart-2027-03",
                "date": "2027-03-15",
                "title": "Certified Basic HART Technology course",
                "tags": ["learning", "practical"],
                "action": "Register",
            },
            {
                "id": "award-2026",
                "date": None,
                "title": "News: Swiss Manufacturing Award 2026",
                "tags": ["news", "special"],
            },
            {
                "id": "singapore",
                "date": None,
                "title": "News: new customer centre in Singapore",
                "tags": ["news"],
            },
        ],
        "policies": {"availability": "Stock and lead times are not public; ask through the customer portal"},
        "provenance": _provenance("https://www.endress.com"),
    },
    {
        "id": "x-adobe",
        "slug": "adobe",
        "kind": "software",
        "name": "Adobe",
        "aliases": ["adobe", "photoshop", "acrobat", "firefly", "express", "content credentials"],
        "tagline": "Creative, document and customer experience software",
        "description": "Creative Cloud (Photoshop, Illustrator, Premiere Pro), Adobe Express, Acrobat and PDF "
        "services, Firefly generative models and Experience Cloud. Co-founded the Content Authenticity Initiative "
        "behind Content Credentials, signed provenance for media. Adobe Experience Manager grew out of Day "
        "Software, a Basel company Adobe acquired in 2010.",
        "website": "https://www.adobe.com",
        "location": "San Jose, USA (headquarters); teams in Basel and worldwide",
        "features": ["creative", "documents", "pdf", "generative ai", "content credentials", "experience cloud"],
        "offers": [
            {
                "id": "express",
                "title": "Adobe Express",
                "summary": "Quick posters, menus and social posts from templates; a free plan exists.",
                "duration": "minutes",
                "price": None,
                "tags": ["short", "calm", "special", "social"],
                "action": "Open Adobe Express",
            },
            {
                "id": "acrobat",
                "title": "Acrobat and Acrobat Sign",
                "summary": "Read, edit, sign and send PDFs.",
                "duration": None,
                "price": None,
                "tags": ["practical", "calm"],
                "action": "Open Acrobat",
            },
            {
                "id": "content-credentials",
                "title": "Content Credentials",
                "summary": "Signed provenance attached to images and video, so anyone can check who made what and "
                "with which tools. The same idea as a signed Hive card, for media.",
                "duration": None,
                "price": None,
                "tags": ["learning"],
                "action": "Learn more",
            },
        ],
        "events": [
            {
                "id": "baselhack-challenge",
                "date": "2026-10-30",
                "title": "Challenge partner at BaselHack 2026: The Post-Website Business",
                "tags": ["news", "learning", "social"],
            },
        ],
        "policies": {},
        "provenance": _provenance("https://www.adobe.com"),
    },
    {
        "id": "x-baselhack",
        "slug": "baselhack",
        "kind": "event",
        "name": "BaselHack",
        "aliases": ["baselhack", "basel hack", "hackathon"],
        "tagline": "48-hour hackathon for the Basel region, since 2017",
        "description": "Run by the BaselHack association. Teams of developers, designers and communicators build "
        "prototypes for partner challenges over one weekend. Free to take part, food and drinks provided. Partners "
        "in 2026 include Adobe, Endress+Hauser, OpenAI, Coop, PAX, Memox and Basel Tech.",
        "website": "https://www.baselhack.ch",
        "location": "Basel",
        "features": ["hackathon", "community", "free", "teams", "prototypes"],
        "offers": [
            {
                "id": "join",
                "title": "Join the community",
                "summary": "Newsletter and Discord for the next edition; non-coders are welcome.",
                "duration": None,
                "price": {"amount": 0, "currency": "CHF", "per": "person", "note": "free to take part"},
                "tags": ["social", "learning", "calm"],
                "action": "Join",
            },
        ],
        "events": [
            {
                "id": "baselhack-2026",
                "date": "2026-10-30",
                "end": "2026-11-01",
                "title": "BaselHack 2026, 48 hours",
                "tags": ["social", "special", "learning"],
            },
        ],
        "policies": {},
        "provenance": _provenance("https://www.baselhack.ch"),
    },
]

KINDS = tuple(sorted({c["kind"] for c in CARDS}))

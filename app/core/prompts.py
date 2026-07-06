"""
Provider-agnostic prompt templates.

All prompts are plain text templates. No provider-specific logic here.
"""

WEBSITE_ANALYSIS_PROMPT = """Analyze the following website for a business redesign opportunity.

Website URL: {url}
Industry: {industry}
Location: {location}

Page content (first 3000 chars):
{page_content}

Analyze and rate (0-100) each dimension:
1. Visual age / modernity
2. Responsiveness
3. Content clarity
4. CTA quality
5. Trust signals
6. Layout density
7. Mobile friendliness

Also list specific design problems and provide an overall weakness score (0-100, higher = weaker site).

Respond in JSON format:
{{
    "visual_age": "description",
    "modernity_score": 0-100,
    "responsiveness": "description",
    "responsiveness_score": 0-100,
    "content_clarity": "description",
    "content_clarity_score": 0-100,
    "cta_quality": "description",
    "cta_score": 0-100,
    "trust_signals": "description",
    "trust_score": 0-100,
    "layout_density": "description",
    "layout_score": 0-100,
    "mobile_friendliness": "description",
    "mobile_score": 0-100,
    "design_problems": ["problem1", "problem2", ...],
    "industry_fit": "description",
    "overall_weakness_score": 0-100,
    "summary": "brief summary"
}}
"""

STYLE_ANALYSIS_PROMPT = """Analyze these design screenshots and extract style signals.

These are past designs created by a web developer. Extract:
1. Color palette (hex codes)
2. Typography style
3. Layout patterns
4. Overall mood/feel
5. Which industries these styles would fit
6. Common design patterns used

Respond in JSON format:
{{
    "color_palette": ["#hex1", "#hex2", ...],
    "typography": "description",
    "layout_style": "description",
    "mood": "description",
    "industry_fit": ["industry1", "industry2", ...],
    "design_patterns": ["pattern1", "pattern2", ...],
    "quality_score": 0-100
}}
"""

HTML_GENERATION_PROMPT = """Generate a complete, modern, responsive HTML landing page for this business.

Business: {company_name}
Industry: {industry}
Location: {location}
Website issues: {design_problems}

Style direction based on our past work:
- Colors: {color_palette}
- Typography: {typography}
- Layout style: {layout_style}
- Mood: {mood}
- Patterns to use: {design_patterns}

Requirements:
- Single HTML file with inline CSS and minimal inline JS
- Mobile-first responsive design
- Modern, clean layout
- Clear hero section with compelling headline
- Service/product highlights section
- Trust signals (testimonials or reviews)
- Clear call-to-action
- Contact information and location
- Footer with business hours
- Use Google Fonts via CDN link
- Use placeholder images from picsum.photos or similar

Generate ONLY the complete HTML code, no explanation.
"""

DESIGN_PLAN_PROMPT = """You are planning a landing page redesign for a real local business. Do not use generic filler.

Business: {company_name}
Industry: {industry}
Location: {location}
Address: {address}
Phone: {phone}
Current website problems: {design_problems}

Style direction:
- Colors: {color_palette}
- Typography: {typography}
- Layout style: {layout_style}
- Mood: {mood}

Produce a concrete content brief for this specific business (not a generic template). Every service/highlight
must be plausible and specific to this industry and business name, not placeholder text like "Quality Service".
If a testimonial is included, it must be clearly labeled as a sample/placeholder, never presented as a real quote.

Respond in JSON format:
{{
    "headline": "specific hero headline",
    "subheadline": "one sentence supporting the headline",
    "sections": ["hero", "..."],
    "highlights": [{{"title": "...", "description": "specific, non-generic description"}}],
    "cta_text": "specific call to action",
    "testimonial_placeholder": "sample quote text, clearly a placeholder",
    "meta_description": "SEO meta description under 160 chars"
}}
"""

HTML_CRITIQUE_PROMPT = """You are a critical design reviewer for a web agency. Review this generated landing page HTML
for {company_name} ({industry}) against commercial-quality standards. Be strict — this will be sent to a real
prospective client as a sample of our work.

HTML:
{html_content}

Check specifically for:
1. Generic filler copy that could apply to any business (bad) vs. specific, plausible content (good)
2. A testimonial presented as a real quote without being marked as a sample (bad)
3. Missing <title> or meta description (bad)
4. Missing viewport meta tag or non-responsive layout (bad)
5. Dead or fabricated links (e.g. guessed email addresses, href="#") (bad)
6. Layout/section structure generic-looking rather than tailored to the industry (bad)

Respond in JSON format:
{{
    "score": 0-100,
    "issues": ["specific issue 1", "specific issue 2", ...],
    "passed": true/false
}}
"""

HTML_REVISION_PROMPT = """Revise the following HTML landing page to fix the listed issues. Keep everything that
already works well. Output the complete corrected HTML file only, no explanation.

Business: {company_name}

Current HTML:
{html_content}

Issues to fix:
{issues}
"""

EMAIL_DRAFT_PROMPT = """Write a professional outreach email to a business owner about redesigning their website.

Business: {company_name}
Industry: {industry}
Location: {location}
Current website problems: {design_problems}
Our redesign approach: {redesign_summary}

The email should:
- Be warm, professional, and concise
- Reference specific issues with their current site (without being insulting)
- Highlight the opportunity for improvement
- Mention that we've prepared a free sample redesign
- Include a clear call to action
- Be under 200 words

Respond in JSON format:
{{
    "subject": "email subject line",
    "body": "email body text"
}}
"""

DISCOVERY_RANKING_PROMPT = """Rank these businesses by redesign opportunity.

Businesses found:
{businesses_json}

Location preference: {location}

Rank them considering:
1. How weak/outdated their website appears
2. Whether they are a brick-and-mortar business
3. Their proximity to {location}
4. Whether redesign would clearly benefit them

Return the top {max_results} as a JSON array:
[
    {{
        "company_name": "...",
        "website_url": "...",
        "industry": "...",
        "location": "...",
        "reason": "why this is a good candidate",
        "estimated_weakness": 0-100
    }}
]
"""

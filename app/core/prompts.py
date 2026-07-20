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

HTML_GENERATION_PROMPT = """You are a senior designer at a boutique web studio, not a template generator.
Generate a complete, modern, responsive HTML landing page for this business that could pass as a
$5,000+ commissioned redesign, not a generic "business website template #4".

Business: {company_name}
Industry: {industry}
Location: {location}
Website issues: {design_problems}

MANDATORY STYLE REQUIREMENTS (you MUST follow these exactly — they come from real design screenshots the developer has created for similar businesses):
- Primary color palette: {color_palette} — use these as your main colors for backgrounds, text, buttons, and accents
- Typography: {typography} — load this SPECIFIC font from Google Fonts and use it for headings
- Layout style: {layout_style}
- Mood/feel: {mood}
- Design patterns to implement: {design_patterns}
- These style traits were extracted from the developer's actual past work for this industry. Follow them closely.

Award-winning reference bar for THIS industry — this is the actual caliber to match, not a
vague "modern" adjective:
{award_reference}

Design quality bar — avoid these "AI template" tells:
- No centered-text-on-a-flat-gradient hero with a single stock photo behind it at 30% opacity. Instead
  vary hero composition: asymmetric split layouts, oversized type as a graphic element, offset image
  crops, layered shapes, or a bold single-color hero with strong typography doing the work.
- No uniform 3-equal-column card grids as the only layout technique. Mix section rhythms: full-bleed
  bands, asymmetric two-column splits, staggered/offset cards, pull quotes, varied vertical spacing.
- No default system fonts (Arial/Helvetica/Roboto) — the specified font must actually load and be visibly
  used for every heading.
- No safe-but-boring color use (navy-on-white, one grey, one blue). Use the given palette boldly: color
  blocks, duotone-style overlays, colored section backgrounds — not just as tiny accent dots.
- Real, generous whitespace and a clear typographic hierarchy (one dominant display size, not five
  similar-sized headings).
- NEVER embed base64-encoded image or SVG data (e.g. `url('data:image/...;base64,...')`) anywhere
  in the HTML or CSS — it burns thousands of tokens for a barely-visible texture and is the single
  biggest cause of the output getting cut off mid-page. For decorative shapes, textures, and
  patterns use pure CSS instead: gradients, clip-path, box-shadow, borders, repeating-linear-gradient,
  and pseudo-elements. This achieves the same visual richness at near-zero cost.

Image policy (follow exactly — broken or irrelevant images are an automatic failure):
{image_instructions}

Contact data for this business (use EXACTLY these values — never invent a phone number,
email address, or booking/ordering URL that isn't listed here):
- Phone: {phone}
- Email: {email}
- Address: {address}
- Original website: {website_url}

FUNCTIONAL LINKS — MANDATORY (a button that goes nowhere is an automatic failure, worse than
no button at all). Every <a> or <button> used as a call-to-action must resolve to exactly one
of these, and nothing else:
1. Call button → href="tel:{phone}" — only if a phone number is listed above; if none is
   listed, do not add a call/phone button at all.
2. Email button → href="mailto:{email}" — only if an email is listed above; if none is
   listed, do not add an email button at all.
3. "Get Directions" / "Find Us" button → href="https://www.google.com/maps/search/?api=1&query=<address>"
   with the address above URL-encoded (spaces as +, commas stripped or encoded).
4. Same-page nav link (e.g. "Menu", "Services", "Contact") → href="#some-id" where an element
   with id="some-id" ACTUALLY EXISTS elsewhere in this same HTML document.
5. Never use href="#" by itself — that is a dead link that does nothing when clicked.
6. Never invent a booking platform, ordering system, or social media URL you have no real data
   for. If there's nothing real to link a CTA to, either drop that CTA entirely or point it at
   the call/email/directions link instead (e.g. "Order by Phone" → tel: link).
7. Every <button> that acts as a CTA must actually be an <a> tag (or wrap one) with one of the
   real hrefs above — a bare <button> with no href and no real destination is a dead click.

Technical requirements:
- Single HTML file with inline CSS and minimal inline JS
- Mobile-first responsive design using CSS Grid or Flexbox
- Use the EXACT colors listed above for hero backgrounds, buttons, and section accents
- Load the specified font from Google Fonts CDN and apply it to headings
- Service/product highlights in a layout that fits the content, not forced into identical boxes
- At least one testimonial section (mark as placeholder/sample)
- Clear call-to-action buttons using the accent color
- Contact section with address and phone
- Footer with business hours

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

Award-winning reference bar for THIS industry (judge criterion 11 against this specifically,
not a generic "looks modern" standard):
{award_reference}

HTML:
{html_content}

Check specifically for:
1. Generic filler copy that could apply to any business (bad) vs. specific, plausible content (good)
2. A testimonial presented as a real quote without being marked as a sample (bad)
3. Missing <title> or meta description (bad)
4. Missing viewport meta tag or non-responsive layout (bad)
5. Non-functional buttons/links — check EVERY <a> and <button> individually:
   - href="#" with no matching id on the page (dead link, does nothing)
   - a <button> with no href and no wrapping <a> (dead click)
   - a mailto:/tel: using an address/number that doesn't match the contact data provided
   - any fabricated external URL (e.g. example.com, a made-up booking/ordering platform) instead
     of the required tel:/mailto:/Google Maps directions/same-page-anchor scheme
   Any single instance of the above is an automatic fail on this criterion.
6. Layout/section structure generic-looking rather than tailored to the industry (bad)
7. Using default/generic fonts like Roboto or system fonts instead of a specific design font (bad)
8. Using bland colors (#333, #fff only) instead of a distinctive branded color palette (bad)
9. No gradient, accent color, or visual flair in the hero section (bad)
10. No CSS Grid or modern layout techniques (bad — plain stacked divs look dated)
11. Fidelity to the attached reference design image(s): does this page's composition, spacing, type
    scale, and overall polish genuinely resemble the caliber and structure of the references — or does
    it look like a generic centered-hero-plus-three-cards AI template regardless of the colors used?
    Be specific about what differs (e.g. "reference uses an asymmetric hero with oversized type; this
    page uses a centered generic hero") (bad if it doesn't resemble the references)
12. Broken or placeholder images: any <img> pointing at a path/service other than the exact local
    "images/..." filenames provided (e.g. picsum.photos, unsplash, any stock/placeholder service),
    or an <img> at all when none were provided (bad — automatic fail). A page with zero photos is
    always better than one with a fake/generic photo.
13. Any base64-encoded image/SVG data (`data:image/...;base64,...`) anywhere in the HTML or CSS —
    always bad, wastes enormous space for a barely-visible effect and risks truncating the page

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

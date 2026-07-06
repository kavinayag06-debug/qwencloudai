"""
HTML Generator Service - generates landing page redesigns.

For each shortlisted client:
- Generates one primary landing page in HTML
- Optionally generates 1-2 alternate variants
- Saves HTML into the output folder
"""

import logging
from pathlib import Path

from app.config import get_settings
from app.core.llm_provider import get_llm_provider
from app.core.models import Lead, LeadStatus, StyleTraits
from app.core.prompts import HTML_GENERATION_PROMPT
from app.storage.database import get_database

logger = logging.getLogger(__name__)

# Industry-specific design presets
INDUSTRY_PRESETS = {
    "florist": {
        "colors": ["#4A7C59", "#F5E6D3", "#D4A574", "#2D5016"],
        "font": "Playfair Display",
        "mood": "elegant, earthy, organic",
        "hero_text": "Beautiful Blooms for Every Occasion",
        "services": ["Wedding Arrangements", "Daily Fresh Bouquets", "Event Floristry"],
        "testimonial": "The most beautiful arrangement I've ever received. Absolutely stunning craftsmanship!",
    },
    "restaurant": {
        "colors": ["#8B1A1A", "#FFF8E7", "#D4A017", "#1A1A1A"],
        "font": "Merriweather",
        "mood": "warm, inviting, appetizing",
        "hero_text": "Authentic Flavours, Unforgettable Moments",
        "services": ["Dine-In Experience", "Catering Services", "Private Events"],
        "testimonial": "Best food in the neighbourhood! We come back every week. The flavours are incredible.",
    },
    "cafe": {
        "colors": ["#6B4423", "#FDF6EC", "#C9956B", "#2C1810"],
        "font": "Nunito",
        "mood": "cozy, artisanal, relaxed",
        "hero_text": "Your Neighbourhood Coffee Spot",
        "services": ["Specialty Coffee", "Fresh Pastries", "Cozy Workspace"],
        "testimonial": "The perfect place to grab a coffee and get some work done. Love the atmosphere!",
    },
    "spa": {
        "colors": ["#5B7B7A", "#F7F3EF", "#C9B99A", "#2C3E3D"],
        "font": "Cormorant Garamond",
        "mood": "serene, luxurious, calming",
        "hero_text": "Relax. Rejuvenate. Restore.",
        "services": ["Massage Therapy", "Facial Treatments", "Body Wellness"],
        "testimonial": "An oasis of calm. I left feeling completely renewed. Can't recommend enough!",
    },
    "salon": {
        "colors": ["#C4547A", "#FFF5F7", "#2C2C2C", "#E8B4B8"],
        "font": "Montserrat",
        "mood": "stylish, confident, trendy",
        "hero_text": "Your Best Look Starts Here",
        "services": ["Haircuts & Styling", "Colour Treatments", "Bridal Packages"],
        "testimonial": "Finally found a salon that really listens. My hair has never looked this good!",
    },
    "gym": {
        "colors": ["#E63946", "#1D3557", "#F1FAEE", "#457B9D"],
        "font": "Oswald",
        "mood": "energetic, powerful, motivating",
        "hero_text": "Push Your Limits. Transform Your Life.",
        "services": ["Personal Training", "Group Classes", "24/7 Access"],
        "testimonial": "This gym changed my life. The trainers are incredible and the community is so supportive.",
    },
    "clinic": {
        "colors": ["#1B6CA8", "#F0F8FF", "#4CAF50", "#2C3E50"],
        "font": "Source Sans Pro",
        "mood": "trustworthy, professional, caring",
        "hero_text": "Compassionate Care for Your Family",
        "services": ["General Consultation", "Health Screening", "Vaccination"],
        "testimonial": "Dr. and the team are always so thorough and kind. We trust them with our whole family's health.",
    },
    "bakery": {
        "colors": ["#D4763B", "#FFF9F0", "#8B4513", "#F5DEB3"],
        "font": "Satisfy",
        "mood": "warm, homely, artisanal",
        "hero_text": "Freshly Baked with Love, Daily",
        "services": ["Artisan Breads", "Custom Cakes", "Pastries & Treats"],
        "testimonial": "The croissants here are better than what I had in Paris. Not exaggerating!",
    },
    "retail": {
        "colors": ["#2C3E50", "#ECF0F1", "#E74C3C", "#3498DB"],
        "font": "Poppins",
        "mood": "modern, clean, trustworthy",
        "hero_text": "Quality Products, Personal Service",
        "services": ["Curated Selection", "Expert Advice", "Local Delivery"],
        "testimonial": "My go-to shop for quality items. The staff really know their products.",
    },
}

DEFAULT_PRESET = {
    "colors": ["#2C3E50", "#ECF0F1", "#3498DB", "#E74C3C"],
    "font": "Inter",
    "mood": "professional, modern",
    "hero_text": "Quality Service You Can Trust",
    "services": ["Expert Service", "Local Presence", "Customer First"],
    "testimonial": "Wonderful experience from start to finish. Highly recommended!",
}


class HTMLGenerator:
    """Generates HTML landing pages based on analysis and style traits."""

    async def generate(self, lead: Lead, style_traits: StyleTraits) -> Lead:
        """Generate an HTML landing page for the lead."""
        logger.info(f"Generating HTML for {lead.company_name}")
        lead.add_log("Starting HTML generation")

        # Prepare prompt
        design_problems = ", ".join(
            lead.website_analysis.design_problems if lead.website_analysis else ["outdated design"]
        )

        prompt = HTML_GENERATION_PROMPT.format(
            company_name=lead.company_name,
            industry=lead.industry,
            location=lead.location,
            design_problems=design_problems,
            color_palette=", ".join(style_traits.color_palette) if style_traits.color_palette else "use industry-appropriate colors",
            typography=style_traits.typography or "modern sans-serif",
            layout_style=style_traits.layout_style or "clean minimalist",
            mood=style_traits.mood or "professional",
            design_patterns=", ".join(style_traits.design_patterns) if style_traits.design_patterns else "hero section, card grid, testimonials, CTA",
        )

        # Generate HTML via LLM
        llm = get_llm_provider()
        try:
            response = await llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=8192,
            )

            html_content = response.content.strip()

            # Clean up if wrapped in code blocks
            if html_content.startswith("```"):
                lines = html_content.split("\n")
                lines = lines[1:]  # Remove opening ```html
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                html_content = "\n".join(lines)

            # Validate it's real HTML
            if not html_content.strip().startswith("<!DOCTYPE") and not html_content.strip().lower().startswith("<html"):
                logger.warning("LLM did not return valid HTML, using industry-specific fallback")
                html_content = self._generate_fallback_html(lead, style_traits)

        except Exception as e:
            logger.error(f"HTML generation failed: {e}")
            lead.add_log(f"HTML generation failed: {str(e)}")
            html_content = self._generate_fallback_html(lead, style_traits)

        # Save HTML file
        settings = get_settings()
        lead_dir = settings.output_dir / lead.id
        lead_dir.mkdir(parents=True, exist_ok=True)

        html_path = lead_dir / "index.html"
        html_path.write_text(html_content, encoding="utf-8")

        lead.html_path = str(html_path)
        lead.status = LeadStatus.REDESIGN_GENERATED
        lead.add_log(f"HTML saved to {html_path}")

        # Save
        db = get_database()
        db.save_lead(lead)
        return lead

    def _generate_fallback_html(self, lead: Lead, style_traits: StyleTraits) -> str:
        """Generate industry-specific fallback HTML."""
        # Get industry preset or default
        industry_key = lead.industry.lower().strip()
        preset = INDUSTRY_PRESETS.get(industry_key, DEFAULT_PRESET)

        # Use style traits colors if available, otherwise use industry preset
        if style_traits.color_palette and len(style_traits.color_palette) >= 3:
            colors = style_traits.color_palette
        else:
            colors = preset["colors"]

        primary = colors[0]
        secondary = colors[1] if len(colors) > 1 else "#F5F5F5"
        accent = colors[2] if len(colors) > 2 else "#3498DB"
        dark = colors[3] if len(colors) > 3 else "#1A1A1A"

        font = preset["font"]
        hero_text = preset["hero_text"]
        services = preset["services"]
        testimonial = preset["testimonial"]

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{lead.company_name} - Redesign Concept</title>
    <link href="https://fonts.googleapis.com/css2?family={font.replace(' ', '+')}:wght@300;400;600;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', sans-serif; color: {dark}; line-height: 1.6; background: #fff; }}
        h1, h2, h3 {{ font-family: '{font}', serif; }}

        .hero {{
            background: linear-gradient(135deg, {primary} 0%, {accent} 100%);
            color: white;
            padding: 100px 20px;
            text-align: center;
            min-height: 70vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        .hero h1 {{ font-size: 3.2rem; margin-bottom: 1rem; font-weight: 700; letter-spacing: -0.02em; }}
        .hero p {{ font-size: 1.25rem; opacity: 0.9; max-width: 600px; margin: 0 auto 2.5rem; }}
        .hero .cta {{
            display: inline-block;
            background: white;
            color: {primary};
            padding: 16px 40px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 600;
            font-size: 1.05rem;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }}
        .hero .cta:hover {{ transform: translateY(-3px); box-shadow: 0 8px 25px rgba(0,0,0,0.2); }}

        .section {{ padding: 80px 20px; max-width: 1100px; margin: 0 auto; }}
        .section h2 {{ font-size: 2.2rem; margin-bottom: 0.75rem; color: {primary}; }}
        .section .subtitle {{ font-size: 1.1rem; color: #666; margin-bottom: 2.5rem; }}

        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 28px;
            margin-top: 2rem;
        }}
        .card {{
            background: {secondary};
            border-radius: 16px;
            padding: 36px 28px;
            text-align: center;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            border: 1px solid rgba(0,0,0,0.04);
        }}
        .card:hover {{ transform: translateY(-4px); box-shadow: 0 12px 40px rgba(0,0,0,0.08); }}
        .card h3 {{ margin-bottom: 0.75rem; color: {primary}; font-size: 1.3rem; }}
        .card p {{ font-size: 0.95rem; color: #555; line-height: 1.7; }}
        .card .icon {{ font-size: 2.5rem; margin-bottom: 1rem; }}

        .testimonials {{
            background: {secondary};
            padding: 80px 20px;
        }}
        .testimonials .inner {{ max-width: 800px; margin: 0 auto; text-align: center; }}
        .testimonials h2 {{ color: {primary}; margin-bottom: 2rem; font-size: 2rem; }}
        .quote {{
            font-size: 1.2rem;
            font-style: italic;
            color: #444;
            line-height: 1.8;
            margin-bottom: 1.5rem;
        }}
        .quote-author {{ font-weight: 600; color: {primary}; }}

        .contact {{
            background: {primary};
            color: white;
            padding: 80px 20px;
            text-align: center;
        }}
        .contact h2 {{ color: white; margin-bottom: 1.5rem; font-size: 2.2rem; }}
        .contact p {{ color: rgba(255,255,255,0.9); font-size: 1.1rem; margin-bottom: 0.5rem; }}
        .contact .cta {{
            display: inline-block;
            margin-top: 2rem;
            background: white;
            color: {primary};
            padding: 14px 36px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
        }}
        .contact .cta:hover {{ transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.2); }}

        footer {{
            background: {dark};
            color: #999;
            padding: 30px 20px;
            text-align: center;
            font-size: 0.85rem;
        }}
        footer a {{ color: {accent}; text-decoration: none; }}

        @media (max-width: 768px) {{
            .hero h1 {{ font-size: 2.2rem; }}
            .hero {{ padding: 60px 16px; min-height: 50vh; }}
            .section {{ padding: 50px 16px; }}
            .cards {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <section class="hero">
        <h1>{lead.company_name}</h1>
        <p>{hero_text}</p>
        <a href="#contact" class="cta">Get in Touch</a>
    </section>

    <section class="section">
        <h2>What We Offer</h2>
        <p class="subtitle">Discover why {lead.location} locals choose us.</p>
        <div class="cards">
            <div class="card">
                <div class="icon">✦</div>
                <h3>{services[0]}</h3>
                <p>Crafted with care and attention to detail, delivering excellence every time.</p>
            </div>
            <div class="card">
                <div class="icon">✦</div>
                <h3>{services[1]}</h3>
                <p>Tailored to your needs with a personal touch that makes all the difference.</p>
            </div>
            <div class="card">
                <div class="icon">✦</div>
                <h3>{services[2]}</h3>
                <p>Going above and beyond to ensure your complete satisfaction.</p>
            </div>
        </div>
    </section>

    <section class="testimonials">
        <div class="inner">
            <h2>What People Say</h2>
            <p class="quote">"{testimonial}"</p>
            <p class="quote-author">— Satisfied Customer</p>
        </div>
    </section>

    <section class="contact" id="contact">
        <h2>Visit Us Today</h2>
        <p>{lead.address or lead.location}</p>
        <p>{lead.phone}</p>
        <a href="mailto:hello@{lead.company_name.lower().replace(' ', '')}.com" class="cta">Contact Us</a>
    </section>

    <footer>
        <p>&copy; 2025 {lead.company_name} &middot; {lead.location} &middot; Redesign concept by <a href="#">QwenCloud AI</a></p>
    </footer>
</body>
</html>"""

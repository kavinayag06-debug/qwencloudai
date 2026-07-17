"""Fallback HTML layouts - structurally different per industry."""

from app.config import get_settings
from app.core.models import Lead, StyleTraits


def _build_map_html(lead: Lead) -> str:
    """Build an interactive Mapbox map embed or a static Google Maps image fallback."""
    settings = get_settings()
    lat = lead.latitude
    lng = lead.longitude

    # If no coordinates, can't show a map
    if not lat or not lng:
        return ""

    # Prefer Mapbox interactive map if key is available
    if settings.mapbox_api_key:
        token = settings.mapbox_api_key
        return f"""<div id="map" style="width:100%;height:300px;border-radius:12px;margin-top:1.5rem;"></div>
<link href="https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.css" rel="stylesheet">
<script src="https://api.mapbox.com/mapbox-gl-js/v3.4.0/mapbox-gl.js"></script>
<script>
mapboxgl.accessToken='{token}';
var map=new mapboxgl.Map({{container:'map',style:'mapbox://styles/mapbox/streets-v12',center:[{lng},{lat}],zoom:15}});
map.addControl(new mapboxgl.NavigationControl());
new mapboxgl.Marker().setLngLat([{lng},{lat}]).addTo(map);
</script>"""

    # Fallback: static Google Maps embed image
    if settings.google_maps_api_key:
        key = settings.google_maps_api_key
        return f'<img src="https://maps.googleapis.com/maps/api/staticmap?center={lat},{lng}&zoom=15&size=600x300&markers=color:red%7C{lat},{lng}&key={key}" alt="Location map" style="width:100%;height:300px;object-fit:cover;border-radius:12px;margin-top:1.5rem;">'

    return ""


def generate_fallback(lead: Lead, style_traits: StyleTraits, presets: dict, default: dict) -> str:
    """Generate fallback HTML with layout variation by industry."""
    industry_key = lead.industry.lower().strip()
    preset = presets.get(industry_key, default)

    if style_traits.color_palette and len(style_traits.color_palette) >= 3:
        colors = style_traits.color_palette
    else:
        colors = preset["colors"]

    p = colors[0]
    s = colors[1] if len(colors) > 1 else "#F5F5F5"
    a = colors[2] if len(colors) > 2 else "#3498DB"
    d = colors[3] if len(colors) > 3 else "#1A1A1A"

    font = preset["font"]
    layout = preset.get("layout", "fullwidth")
    hero = preset["hero_text"]
    svcs = preset["services"]
    quote = preset["testimonial"]
    name = lead.company_name
    addr = lead.address or lead.location
    phone = lead.phone or ""

    # Map embed
    map_html = _build_map_html(lead)

    # Client images
    imgs = ""
    if hasattr(lead, 'local_image_paths') and lead.local_image_paths:
        imgs = "".join(
            f'<img src="images/{nm}" alt="{name}" style="width:100%;height:280px;object-fit:cover;border-radius:12px;">'
            for nm in lead.local_image_paths[:3]
        )

    layouts = {
        "angular": _angular,
        "minimal": _minimal,
        "bold": _bold,
        "split": _split,
        "warm": _warm,
        "editorial": _editorial,
        "clean": _clean,
        "grid": _grid,
    }
    fn = layouts.get(layout, _fullwidth)
    return fn(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html)


def _fullwidth(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;padding:40px 20px;max-width:1100px;margin:0 auto">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@400;700&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',sans-serif;color:{d}}}
.hero{{background:linear-gradient(135deg,{p},{a});color:#fff;padding:120px 20px;text-align:center;min-height:75vh;display:flex;flex-direction:column;justify-content:center}}
.hero h1{{font-size:3.5rem;margin-bottom:1rem}}.hero p{{font-size:1.2rem;opacity:.9;max-width:600px;margin:0 auto 2rem}}
.btn{{display:inline-block;background:#fff;color:{p};padding:16px 40px;border-radius:50px;text-decoration:none;font-weight:700}}
.grid{{padding:80px 20px;max-width:1100px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:28px}}
.card{{background:{s};padding:36px;border-radius:16px;text-align:center}}.card h3{{color:{p};margin-bottom:.5rem}}
.qt{{background:{s};padding:80px 20px;text-align:center}}.qt p{{font-size:1.2rem;font-style:italic;max-width:700px;margin:0 auto}}
.ct{{background:{p};color:#fff;padding:80px 20px;text-align:center}}.ct h2{{margin-bottom:1rem}}
footer{{background:{d};color:#888;padding:24px;text-align:center;font-size:.85rem}}
@media(max-width:768px){{.hero h1{{font-size:2.2rem}}}}</style></head><body>
<section class="hero"><h1>{name}</h1><p>{hero}</p><a href="#ct" class="btn">Get in Touch</a></section>
{gal}
<section class="grid"><div class="card"><h3>{svcs[0]}</h3><p>Excellence delivered every time.</p></div><div class="card"><h3>{svcs[1]}</h3><p>Tailored to your needs.</p></div><div class="card"><h3>{svcs[2]}</h3><p>Going above and beyond.</p></div></section>
<section class="qt"><p>"{quote}"</p><p style="margin-top:1rem;font-weight:600">— Sample review</p></section>
<section class="ct" id="ct"><h2>Visit Us</h2><p>{addr}</p><p>{phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _angular(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="display:flex;gap:8px;padding:20px;max-width:1000px;margin:0 auto;overflow:hidden">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@400;700;900&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',sans-serif;color:#fff;background:{d}}}
.hero{{background:{p};padding:100px 20px;clip-path:polygon(0 0,100% 0,100% 85%,0 100%);min-height:70vh;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center}}
.hero h1{{font-size:4rem;font-weight:900;text-transform:uppercase;letter-spacing:3px}}.hero p{{font-size:1.1rem;margin:1rem 0 2rem;opacity:.9}}
.btn{{background:{a};color:#fff;padding:16px 36px;text-decoration:none;font-weight:700;text-transform:uppercase;letter-spacing:1px}}
.feats{{padding:100px 20px 60px;max-width:1000px;margin:0 auto;display:grid;grid-template-columns:repeat(3,1fr);gap:24px}}
.ft{{border-left:4px solid {a};padding:20px;background:rgba(255,255,255,.05)}}.ft h3{{color:{a};text-transform:uppercase;margin-bottom:.5rem}}.ft p{{color:#aaa;font-size:.9rem}}
.cta-bar{{background:{a};padding:60px 20px;text-align:center;clip-path:polygon(0 15%,100% 0,100% 100%,0 100%)}}.cta-bar h2{{font-size:2rem;margin-bottom:.5rem}}
footer{{background:#111;color:#555;padding:20px;text-align:center;font-size:.8rem}}
@media(max-width:768px){{.hero h1{{font-size:2.2rem}}.feats{{grid-template-columns:1fr}}.hero{{clip-path:none}}}}</style></head><body>
<section class="hero"><h1>{name}</h1><p>{hero}</p><a href="#cta" class="btn">Join Now</a></section>
{gal}
<section class="feats"><div class="ft"><h3>{svcs[0]}</h3><p>Push beyond limits.</p></div><div class="ft"><h3>{svcs[1]}</h3><p>Together we achieve more.</p></div><div class="ft"><h3>{svcs[2]}</h3><p>Always ready.</p></div></section>
<section class="cta-bar" id="cta"><h2>Ready?</h2><p>{addr} &middot; {phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _minimal(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:40px 0">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@300;400;600&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',sans-serif;color:{d};background:{s}}}
.c{{max-width:760px;margin:0 auto;padding:0 24px}}
.hero{{padding:140px 0 60px}}.hero h1{{font-size:3rem;font-weight:300;color:{p};line-height:1.2}}.hero p{{color:#666;margin:1.5rem 0;max-width:480px}}
.hero a{{color:{p};font-weight:600;text-decoration:underline}}
.div{{width:50px;height:2px;background:{p};margin:50px 0}}
.list{{list-style:none}}.list li{{padding:20px 0;border-bottom:1px solid rgba(0,0,0,.06);font-size:1.05rem;display:flex;justify-content:space-between}}.list li span{{color:{p};font-weight:600}}
.qb{{margin:60px 0;padding:36px;background:#fff;border-left:3px solid {p};border-radius:0 10px 10px 0}}.qb p{{font-style:italic;color:#555}}
.foot{{margin-top:80px;padding:30px 0;border-top:1px solid rgba(0,0,0,.08);font-size:.85rem;color:#aaa}}
</style></head><body><div class="c">
<section class="hero"><h1>{name}</h1><p>{hero}</p><a href="#contact">Visit &rarr;</a></section>
<div class="div"></div>
{gal}
<ul class="list"><li>{svcs[0]}<span>&rarr;</span></li><li>{svcs[1]}<span>&rarr;</span></li><li>{svcs[2]}<span>&rarr;</span></li></ul>
<div class="qb"><p>"{quote}"</p><p style="margin-top:10px;font-style:normal;font-size:.85rem">— Sample</p></div>
<section id="contact"><p>{addr}</p><p>{phone}</p>{map_html}</section>
<footer class="foot">&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></div></body></html>"""


def _bold(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:4px;padding:20px">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@400;700;800&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',sans-serif;color:{s};background:{d}}}
.hero{{min-height:90vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:40px;background:radial-gradient(ellipse at center,{a}22,transparent 70%)}}
.hero h1{{font-size:4.5rem;font-weight:800;color:{p};text-transform:uppercase;letter-spacing:-2px}}.hero p{{font-size:1.1rem;opacity:.6;margin:1rem 0 2rem}}
.btn{{background:{p};color:#fff;padding:16px 40px;border-radius:50px;text-decoration:none;font-weight:700}}
.strip{{display:flex}}.si{{flex:1;padding:50px 24px;text-align:center;border-right:1px solid rgba(255,255,255,.05)}}.si h3{{color:{p};margin-bottom:.5rem}}.si p{{font-size:.85rem;opacity:.5}}
.td{{padding:80px 20px;text-align:center;border-top:1px solid rgba(255,255,255,.05)}}.td p{{font-size:1.2rem;font-style:italic;max-width:600px;margin:0 auto;opacity:.7}}
.cd{{padding:60px 20px;text-align:center}}.cd h2{{color:{p};margin-bottom:.5rem}}
footer{{padding:20px;text-align:center;font-size:.75rem;opacity:.3}}
@media(max-width:768px){{.hero h1{{font-size:2.5rem}}.strip{{flex-direction:column}}}}</style></head><body>
<section class="hero"><h1>{name}</h1><p>{hero}</p><a href="#cd" class="btn">Book Now</a></section>
{gal}
<section class="strip"><div class="si"><h3>{svcs[0]}</h3><p>Confidence starts here.</p></div><div class="si"><h3>{svcs[1]}</h3><p>Expertly crafted.</p></div><div class="si"><h3>{svcs[2]}</h3><p>Elevated style.</p></div></section>
<section class="td"><p>"{quote}"</p><p style="margin-top:1rem;opacity:.4;font-style:normal">— Sample</p></section>
<section class="cd" id="cd"><h2>Find Us</h2><p>{addr}</p><p>{phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _split(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;padding:40px;max-width:1100px;margin:0 auto">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',serif;color:{d};background:#fff}}
.split{{display:grid;grid-template-columns:1fr 1fr;min-height:100vh}}.st{{display:flex;flex-direction:column;justify-content:center;padding:60px}}
.sv{{background:linear-gradient(160deg,{p},{a});position:relative;overflow:hidden}}
.sv::after{{content:'';position:absolute;inset:0;background:repeating-linear-gradient(45deg,transparent,transparent 20px,rgba(255,255,255,.03) 20px,rgba(255,255,255,.03) 40px)}}
.st h1{{font-size:3rem;color:{p};font-weight:300;margin-bottom:1rem}}.st p{{color:#666;margin-bottom:2rem;line-height:1.8}}
.btn{{display:inline-block;background:{p};color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600}}
.feats{{padding:80px 40px;display:grid;grid-template-columns:repeat(3,1fr);gap:32px;max-width:1100px;margin:0 auto}}
.ft{{text-align:center}}.ft h3{{color:{p};margin-bottom:.5rem}}.ft p{{color:#777;font-size:.9rem}}
.bot{{background:{s};padding:80px 40px;text-align:center}}.bot .q{{font-style:italic;font-size:1.15rem;max-width:600px;margin:0 auto 1.5rem;color:#555}}
footer{{padding:20px;text-align:center;font-size:.8rem;color:#aaa}}
@media(max-width:768px){{.split{{grid-template-columns:1fr}}.sv{{min-height:40vh}}.feats{{grid-template-columns:1fr;padding:40px 20px}}}}</style></head><body>
<section class="split"><div class="st"><h1>{name}</h1><p>{hero}</p><a href="#bot" class="btn">Explore</a></div><div class="sv"></div></section>
{gal}
<section class="feats"><div class="ft"><h3>{svcs[0]}</h3><p>Nature's finest.</p></div><div class="ft"><h3>{svcs[1]}</h3><p>Fresh and seasonal.</p></div><div class="ft"><h3>{svcs[2]}</h3><p>Memorable moments.</p></div></section>
<section class="bot" id="bot"><p class="q">"{quote}"</p><p>{addr} &middot; {phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _warm(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;padding:20px;max-width:900px;margin:0 auto">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@400;700&family=Inter:wght@400&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'Inter',sans-serif;color:{d};background:{s}}}
h1,h2,h3{{font-family:'{font}',cursive}}
.hero{{background:{p};color:#fff;padding:80px 20px;border-radius:0 0 40px 40px;text-align:center}}
.hero h1{{font-size:3.5rem;margin-bottom:.5rem}}.hero p{{opacity:.9;max-width:500px;margin:0 auto}}
.menu{{max-width:900px;margin:60px auto;padding:0 20px}}.menu h2{{text-align:center;color:{p};margin-bottom:2rem}}
.mg{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px}}
.mc{{background:#fff;border-radius:20px;padding:28px;text-align:center;box-shadow:0 4px 16px rgba(0,0,0,.04)}}.mc h3{{color:{p};margin-bottom:.5rem}}.mc p{{color:#777;font-size:.9rem}}
.wb{{background:#fff;border-radius:24px;max-width:660px;margin:40px auto;padding:44px;text-align:center}}.wb p{{font-size:1.1rem;font-style:italic;color:#666}}
.visit{{text-align:center;padding:60px 20px}}.visit h2{{color:{p};margin-bottom:.5rem}}
footer{{text-align:center;padding:20px;font-size:.8rem;color:#bbb}}
@media(max-width:768px){{.hero h1{{font-size:2.2rem}}.hero{{border-radius:0 0 20px 20px}}}}</style></head><body>
<section class="hero"><h1>{name}</h1><p>{hero}</p></section>
{gal}
<section class="menu"><h2>Our Specialties</h2><div class="mg"><div class="mc"><h3>{svcs[0]}</h3><p>Made with love daily.</p></div><div class="mc"><h3>{svcs[1]}</h3><p>For special celebrations.</p></div><div class="mc"><h3>{svcs[2]}</h3><p>A treat for any moment.</p></div></div></section>
<div class="wb"><p>"{quote}"</p><p style="margin-top:10px;font-style:normal;font-weight:600;color:{p}">— Sample</p></div>
<section class="visit" id="contact"><h2>Come Say Hello</h2><p>{addr}</p><p>{phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _editorial(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    gal = f'<div style="columns:2;gap:12px;padding:40px 20px;max-width:900px;margin:0 auto">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@400;700&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',serif;color:{d};background:{s}}}
.hero{{min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;border-bottom:1px solid rgba(0,0,0,.05)}}
.hero h1{{font-size:5rem;font-weight:400;letter-spacing:-3px;color:{p}}}.hero p{{font-size:1rem;text-transform:uppercase;letter-spacing:4px;margin-top:1rem;color:{a}}}
.row{{display:grid;grid-template-columns:1fr 1fr;max-width:1000px;margin:80px auto;gap:60px;padding:0 40px;align-items:center}}
.row h2{{font-size:2rem;color:{p}}}.row p{{color:#666;line-height:1.8;margin-top:1rem}}
.row-r{{text-align:right}}
.ft{{background:{p};color:#fff;padding:80px 40px;text-align:center}}.ft h2{{margin-bottom:1rem}}.ft p{{opacity:.8}}
footer{{padding:20px;text-align:center;font-size:.8rem;color:#aaa}}
@media(max-width:768px){{.hero h1{{font-size:2.5rem}}.row{{grid-template-columns:1fr;padding:0 20px;gap:30px}}}}</style></head><body>
<section class="hero"><div><h1>{name}</h1><p>{hero}</p></div></section>
{gal}
<section class="row"><div><h2>{svcs[0]}</h2><p>Curated with an editorial eye.</p></div><div class="row-r"><h2>{svcs[1]}</h2><p>For those who appreciate the finer details.</p></div></section>
<section class="ft" id="contact"><h2>Visit</h2><p>{addr} &middot; {phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _clean(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    """Medical/clinic style - clean, lots of white, trust-focused."""
    gal = f'<div style="display:flex;gap:16px;padding:40px 20px;max-width:1000px;margin:0 auto;overflow-x:auto">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@300;400;600&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',sans-serif;color:{d};background:#fff}}
.top-bar{{background:{p};color:#fff;padding:12px 20px;text-align:center;font-size:.9rem}}
.hero{{padding:100px 20px;max-width:800px;margin:0 auto;text-align:center}}.hero h1{{font-size:2.5rem;font-weight:300;color:{p};margin-bottom:1rem}}
.hero p{{color:#666;font-size:1.1rem;margin-bottom:2rem}}.btn{{background:{a};color:#fff;padding:14px 32px;border-radius:8px;text-decoration:none;font-weight:600}}
.trust{{display:flex;justify-content:center;gap:40px;padding:40px 20px;border-top:1px solid #eee;border-bottom:1px solid #eee}}
.trust-item{{text-align:center;font-size:.9rem;color:#888}}.trust-item strong{{display:block;font-size:1.5rem;color:{p}}}
.services-clean{{max-width:800px;margin:60px auto;padding:0 20px}}.sc{{padding:24px 0;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:16px}}
.sc-dot{{width:10px;height:10px;border-radius:50%;background:{a}}}.sc h3{{color:{d};font-weight:400}}
.contact-clean{{background:{s};padding:60px 20px;text-align:center;margin-top:60px}}.contact-clean h2{{color:{p};margin-bottom:1rem}}
footer{{padding:20px;text-align:center;font-size:.8rem;color:#bbb}}
@media(max-width:768px){{.trust{{flex-direction:column;gap:20px}}}}</style></head><body>
<div class="top-bar">Caring for your family's health since day one</div>
<section class="hero"><h1>{name}</h1><p>{hero}</p><a href="#contact" class="btn">Book Appointment</a></section>
{gal}
<section class="trust"><div class="trust-item"><strong>15+</strong>Years Experience</div><div class="trust-item"><strong>5000+</strong>Patients Served</div><div class="trust-item"><strong>4.9</strong>Rating</div></section>
<section class="services-clean"><div class="sc"><div class="sc-dot"></div><h3>{svcs[0]}</h3></div><div class="sc"><div class="sc-dot"></div><h3>{svcs[1]}</h3></div><div class="sc"><div class="sc-dot"></div><h3>{svcs[2]}</h3></div></section>
<section class="contact-clean" id="contact"><h2>Visit Us</h2><p>{addr}</p><p>{phone}</p>{map_html}</section>
<footer>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</footer></body></html>"""


def _grid(name, p, s, a, d, font, hero, svcs, quote, addr, phone, imgs, map_html):
    """Retail/product grid style."""
    gal = f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;padding:20px;max-width:1000px;margin:0 auto">{imgs}</div>' if imgs else ''
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name}</title><link href="https://fonts.googleapis.com/css2?family={font.replace(' ','+')}:wght@400;600;700&display=swap" rel="stylesheet">
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:'{font}',sans-serif;color:{d};background:#fafafa}}
nav{{background:#fff;padding:16px 24px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #eee;position:sticky;top:0;z-index:10}}
nav h1{{font-size:1.2rem;color:{p}}}nav a{{color:{p};text-decoration:none;font-weight:600}}
.banner{{background:{p};color:#fff;padding:60px 20px;text-align:center}}.banner h2{{font-size:2.5rem;margin-bottom:.5rem}}.banner p{{opacity:.9}}
.products{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;padding:40px 20px;max-width:1100px;margin:0 auto}}
.prod{{background:#fff;border-radius:12px;padding:24px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.04)}}.prod h3{{color:{p};margin-bottom:.5rem}}.prod p{{color:#888;font-size:.9rem}}
.prod .price{{margin-top:12px;font-weight:700;color:{a}}}
.info{{max-width:800px;margin:40px auto;padding:40px;text-align:center}}.info p{{color:#666;font-style:italic}}
footer{{background:{d};color:#888;padding:24px;text-align:center;font-size:.8rem}}
</style></head><body>
<nav><h1>{name}</h1><a href="#contact">Contact</a></nav>
<section class="banner"><h2>{hero}</h2><p>Shop the collection</p></section>
{gal}
<section class="products"><div class="prod"><h3>{svcs[0]}</h3><p>Hand-picked quality.</p><p class="price">View &rarr;</p></div><div class="prod"><h3>{svcs[1]}</h3><p>Expert recommendations.</p><p class="price">View &rarr;</p></div><div class="prod"><h3>{svcs[2]}</h3><p>Delivered to your door.</p><p class="price">View &rarr;</p></div></section>
<section class="info"><p>"{quote}"</p></section>
<footer id="contact"><p>{addr} &middot; {phone}</p>{map_html}<p>&copy; 2025 {name} &middot; Redesign by QwenCloud AI</p></footer></body></html>"""

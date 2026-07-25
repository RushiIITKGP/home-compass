"""
Generates compliance/data/fhas_part12_rules.pdf — a FICTIONAL,
government-style rulebook the compliance guardrail RAG pipeline ingests.

Why fictional: real analogues exist (HUD's Part 109 Fair Housing
Advertising regulations, the Fair Housing Act itself) and this pipeline
can ingest them too — drop any rules PDF into compliance/data/ and
re-run ingest_rules.py. But for development we want a document whose
contents we fully control, so eval cases can assert "this answer
violates §12.4" without depending on a third-party PDF's wording.
The rules are modeled on real Fair Housing themes so the guardrail
behavior transfers to the real thing.

Every rule is numbered "§ 12.N" — ingest_rules.py chunks on exactly
that marker, one chunk per rule, so retrieval returns whole rules with
their section numbers intact (citable by the guardrail).

Usage:  python compliance/generate_rules_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent / "data" / "fhas_part12_rules.pdf"

styles = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=styles["Title"], fontSize=16, leading=20, alignment=TA_CENTER),
    "subtitle": ParagraphStyle("st", parent=styles["Normal"], fontSize=11, leading=15, alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", parent=styles["Heading1"], fontSize=13, spaceBefore=18),
    "rule": ParagraphStyle("r", parent=styles["Heading2"], fontSize=11.5, spaceBefore=14, spaceAfter=4),
    "body": ParagraphStyle("b", parent=styles["Normal"], fontSize=10, leading=14, alignment=TA_JUSTIFY),
    "note": ParagraphStyle("n", parent=styles["Normal"], fontSize=8.5, leading=11, textColor="#555555"),
}


def body(text: str) -> Paragraph:
    return Paragraph(text, S["body"])


RULES = [
    (
        "§ 12.1 Prohibition on Steering by Protected Characteristic",
        "An advisory service shall not recommend, discourage, rank, or filter properties, "
        "neighborhoods, or communities on the basis of the race, color, religion, national "
        "origin, sex, disability, or familial status of any person, whether of the prospective "
        "buyer or of the residents of any area. An advisory service shall not answer, in "
        "affirmative or negative terms, any inquiry that asks it to characterize the suitability "
        "of a neighborhood for persons of a protected class, including inquiries phrased as "
        "questions about where such persons 'would feel comfortable' or 'fit in.' The service "
        "shall instead state that it cannot advise on the basis of protected characteristics and "
        "may offer objective, sourced data as described in § 12.2.",
    ),
    (
        "§ 12.2 Presentation of Demographic Data",
        "An advisory service may present demographic statistics concerning an area only where "
        "(a) the statistic is drawn from an identified governmental or published statistical "
        "source; (b) the source and reference period are stated adjacent to the figure; and "
        "(c) the statistic is presented without characterization. Words and phrases that assign "
        "social value to demographic composition — including but not limited to 'good area,' "
        "'desirable community,' 'safe kind of people,' 'family-friendly demographics,' or "
        "'up-and-coming crowd' — constitute prohibited characterization when tied to "
        "demographic data.",
    ),
    (
        "§ 12.3 Crime and Safety Information",
        "Crime statistics shall be presented only with an identified source, jurisdiction, and "
        "reporting year, and shall not be extrapolated to years, areas, or geographic levels not "
        "covered by the source. An advisory service shall not describe any area as 'safe' or "
        "'dangerous' in absolute terms; it may state reported counts or rates and their source. "
        "Where crime data is unavailable for an area, the service shall state that it is "
        "unavailable and shall not substitute an estimate, an inference from adjacent areas, or "
        "a general impression.",
    ),
    (
        "§ 12.4 Financial Representations",
        "An advisory service shall not represent, promise, or forecast the future value, "
        "appreciation, rental yield, or investment return of any property. Historical market "
        "statistics may be presented subject to the sourcing requirements of § 12.2. Any "
        "discussion of affordability, financing, mortgages, or monthly cost shall be accompanied "
        "by a statement that the service is not a licensed financial advisor and that figures "
        "are estimates, and the consumer shall be directed to consult a licensed professional "
        "before making financial decisions.",
    ),
    (
        "§ 12.5 Accuracy and Verification of Listing Information",
        "An advisory service shall present as fact only listing attributes present in its "
        "records at the time of response. Attributes not present in the record — including "
        "school quality, renovation condition, lot features, HOA terms, and days on market — "
        "shall not be asserted, estimated, or implied. Where a consumer asks about an attribute "
        "the service does not hold, the service shall state that the information is not in its "
        "records and identify where the consumer may verify it.",
    ),
    (
        "§ 12.6 Source Attribution",
        "Each statistic concerning demographics, crime, or market conditions presented to a "
        "consumer shall carry an attribution sufficient to identify the originating dataset and "
        "period. Aggregated or blended figures that cannot be attributed to a single source "
        "shall be identified as derived figures, with each contributing source named.",
    ),
    (
        "§ 12.7 Advertising and Descriptive Language",
        "An advisory service shall not employ words, phrases, or symbols conveying an overt or "
        "tacit preference or limitation based on a protected characteristic. Prohibited terms "
        "include, without limitation: 'exclusive neighborhood,' 'traditional community,' "
        "'perfect for young professionals,' 'ideal for families with children' (as a preference "
        "rather than an objective attribute), 'no students,' and geographic euphemisms commonly "
        "understood to signal demographic composition. Objective property attributes (bedroom "
        "count, square footage, accessibility features) are not restricted by this section.",
    ),
    (
        "§ 12.8 Consumer Privacy and Data Minimization",
        "An advisory service shall not request, encourage the disclosure of, or retain a "
        "consumer's Social Security number, financial account numbers, government identification "
        "numbers, or medical information. Where a consumer volunteers such information, the "
        "service shall not repeat it in any response, shall not incorporate it into stored "
        "preferences, and shall advise the consumer that such information is not required to "
        "receive advisory services.",
    ),
    (
        "§ 12.9 Disclosure of Automated Operation",
        "Upon inquiry, an advisory service shall accurately disclose that responses are "
        "generated by an automated system. An advisory service shall not claim licensure, "
        "certification, brokerage affiliation, or personal experience it does not possess, and "
        "shall not represent automated output as the individualized judgment of a licensed "
        "professional.",
    ),
    (
        "§ 12.10 Referral to Licensed Professionals",
        "Where a consumer inquiry concerns contract terms, legal obligations, inspection "
        "findings, title matters, or tax consequences, the advisory service shall state that "
        "the matter requires a licensed professional and identify the appropriate category of "
        "professional (attorney, licensed broker, inspector, or tax advisor). The service may "
        "provide general educational information on such topics only when accompanied by that "
        "referral.",
    ),
]


def build() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=letter,
        leftMargin=1 * inch, rightMargin=1 * inch, topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        title="FHAS Part 12 — Standards of Conduct for Automated Real Estate Advisory Services",
    )
    story = []

    # ---- page 1: cover / preamble ----
    story.append(Spacer(1, 60))
    story.append(Paragraph("FEDERAL HOUSING ADVISORY STANDARDS", S["title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("PART 12 — STANDARDS OF CONDUCT FOR AUTOMATED<br/>REAL ESTATE ADVISORY SERVICES", S["subtitle"]))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Office of Housing Technology Oversight<br/>Edition of March 2026", S["subtitle"]))
    story.append(Spacer(1, 40))
    story.append(body(
        "PREAMBLE. This Part establishes minimum standards of conduct for automated and "
        "artificial-intelligence-assisted services that advise consumers in residential real "
        "estate transactions. It is issued to ensure that the efficiencies of automated advice "
        "do not erode the protections consumers hold under fair housing, consumer protection, "
        "and privacy law. Operators of advisory services shall ensure conformity with each "
        "section of this Part and shall maintain records sufficient to demonstrate such "
        "conformity upon audit."
    ))
    story.append(Spacer(1, 24))
    story.append(Paragraph(
        "NOTICE — FICTIONAL DOCUMENT. This document is a fictional training artifact created "
        "for the Home Compass project. It is not issued by any government and has no legal "
        "force. Its rules are modeled on themes from real fair-housing law (e.g., 24 C.F.R. "
        "Part 109) for realistic development and testing of compliance guardrails.", S["note"],
    ))
    story.append(PageBreak())

    # ---- page 2: definitions & scope ----
    story.append(Paragraph("SUBPART A — GENERAL PROVISIONS", S["h1"]))
    story.append(Paragraph("§ 12.0 Scope and Definitions", S["rule"]))
    story.append(body(
        "(a) <b>Advisory service</b> means any automated system, including systems employing "
        "large language models, that recommends properties, characterizes neighborhoods, or "
        "otherwise advises consumers in connection with the purchase, sale, or rental of "
        "residential real estate. (b) <b>Protected characteristic</b> means race, color, "
        "religion, national origin, sex, disability, or familial status. (c) <b>Consumer</b> "
        "means any natural person interacting with an advisory service. (d) <b>Record</b> means "
        "structured data held by the operator at the time a response is generated. (e) This "
        "Part applies to every consumer-facing response of an advisory service, including "
        "clarifying questions, search results, and narrative commentary."
    ))
    story.append(Paragraph("§ 12.0.1 Construction", S["rule"]))
    story.append(body(
        "Where a response could be construed either to comply with or to violate this Part, "
        "the construction favoring consumer protection governs. Ambiguity in a consumer's "
        "inquiry does not excuse a non-conforming response; the advisory service shall seek "
        "clarification or decline in conforming terms."
    ))
    story.append(PageBreak())

    # ---- pages 3-5: the rules ----
    story.append(Paragraph("SUBPART B — CONDUCT RULES", S["h1"]))
    for i, (heading, text) in enumerate(RULES):
        story.append(Paragraph(heading, S["rule"]))
        story.append(body(text))
        if i in (2, 5, 7):  # page breaks roughly every 3 rules
            story.append(PageBreak())

    # ---- final page: enforcement ----
    story.append(PageBreak())
    story.append(Paragraph("SUBPART C — ENFORCEMENT", S["h1"]))
    story.append(Paragraph("§ 12.20 Remediation of Non-Conforming Responses", S["rule"]))
    story.append(body(
        "An operator that detects a non-conforming response prior to or upon delivery shall "
        "suppress or revise the response to conform with this Part, and the revised response "
        "shall identify, by section number, the standard that required revision where doing so "
        "aids consumer understanding. Repeated non-conformity of the same class shall be "
        "treated as a systemic defect requiring corrective change to the advisory service "
        "itself, not merely per-response revision."
    ))
    story.append(Paragraph("§ 12.21 Audit Trail", S["rule"]))
    story.append(body(
        "Operators shall retain, for each consumer interaction, a trace sufficient to "
        "reconstruct the inputs, retrieved data, and rule determinations underlying each "
        "response, and shall make such traces available for compliance review."
    ))

    doc.build(story)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()

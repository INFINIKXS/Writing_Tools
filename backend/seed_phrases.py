"""
Seed script — populates the Supabase 'phrases' table with curated
academic phrase templates across 11 rhetorical categories.

Run once:  python seed_phrases.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from db.supabase_client import supabase

PHRASES = [
    # ── Stating the Aim ──────────────────────────────────────────────
    {"template": "This study aims to [X] by [Y]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "This study aims to examine writing patterns by analysing student essays.", "formality_level": "formal"},
    {"template": "The purpose of this paper is to [X]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "The purpose of this paper is to investigate the relationship between sleep and academic performance.", "formality_level": "formal"},
    {"template": "This paper seeks to address [X] by [Y]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "This paper seeks to address the gap in knowledge by conducting a longitudinal study.", "formality_level": "formal"},
    {"template": "The primary objective of this research is to [X]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "The primary objective of this research is to determine the efficacy of the intervention.", "formality_level": "formal"},
    {"template": "This investigation sets out to [X]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "This investigation sets out to explore how environmental factors influence behaviour.", "formality_level": "formal"},
    {"template": "The present study was designed to [X]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "The present study was designed to test the hypothesis that early intervention improves outcomes.", "formality_level": "formal"},
    {"template": "In this paper, we attempt to [X]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "In this paper, we attempt to reconcile conflicting findings from previous research.", "formality_level": "formal"},
    {"template": "The aim of this study is to shed light on [X]", "category": "Stating the Aim", "subcategory": "Research Purpose", "example": "The aim of this study is to shed light on the mechanisms underlying cognitive decline.", "formality_level": "formal"},
    {"template": "This research examines [X] with particular focus on [Y]", "category": "Stating the Aim", "subcategory": "Scope", "example": "This research examines urban development with particular focus on housing affordability.", "formality_level": "formal"},
    {"template": "The central question addressed in this study is [X]", "category": "Stating the Aim", "subcategory": "Research Question", "example": "The central question addressed in this study is whether social media usage affects attention spans.", "formality_level": "formal"},

    # ── Reviewing the Literature ─────────────────────────────────────
    {"template": "Several studies have suggested that [X]", "category": "Reviewing the Literature", "subcategory": "Citing Previous Work", "example": "Several studies have suggested that regular exercise improves cognitive function.", "formality_level": "formal"},
    {"template": "A growing body of literature has examined [X]", "category": "Reviewing the Literature", "subcategory": "Citing Previous Work", "example": "A growing body of literature has examined the impact of screen time on children's development.", "formality_level": "formal"},
    {"template": "Previous research has established that [X]", "category": "Reviewing the Literature", "subcategory": "Citing Previous Work", "example": "Previous research has established that bilingualism confers cognitive advantages.", "formality_level": "formal"},
    {"template": "The concept of [X] has been widely discussed in [Y]", "category": "Reviewing the Literature", "subcategory": "Theoretical Background", "example": "The concept of social capital has been widely discussed in sociological literature.", "formality_level": "formal"},
    {"template": "Much of the current literature on [X] pays particular attention to [Y]", "category": "Reviewing the Literature", "subcategory": "Focus Areas", "example": "Much of the current literature on climate change pays particular attention to carbon emissions.", "formality_level": "formal"},
    {"template": "Recent evidence suggests that [X]", "category": "Reviewing the Literature", "subcategory": "Citing Previous Work", "example": "Recent evidence suggests that mindfulness-based interventions reduce anxiety symptoms.", "formality_level": "formal"},
    {"template": "It is now well established from a variety of studies that [X]", "category": "Reviewing the Literature", "subcategory": "Consensus", "example": "It is now well established from a variety of studies that smoking causes lung cancer.", "formality_level": "formal"},
    {"template": "A number of studies have found that [X]", "category": "Reviewing the Literature", "subcategory": "Citing Previous Work", "example": "A number of studies have found that peer feedback improves writing quality.", "formality_level": "formal"},
    {"template": "There is a large volume of published studies describing [X]", "category": "Reviewing the Literature", "subcategory": "Research Landscape", "example": "There is a large volume of published studies describing the role of genetics in obesity.", "formality_level": "formal"},
    {"template": "What we know about [X] is largely based on [Y]", "category": "Reviewing the Literature", "subcategory": "Methodological Context", "example": "What we know about deep-sea ecosystems is largely based on remote observation techniques.", "formality_level": "formal"},

    # ── Identifying a Gap ────────────────────────────────────────────
    {"template": "However, little is known about [X]", "category": "Identifying a Gap", "subcategory": "Knowledge Gap", "example": "However, little is known about the long-term effects of this treatment.", "formality_level": "formal"},
    {"template": "No study to date has examined [X]", "category": "Identifying a Gap", "subcategory": "Research Gap", "example": "No study to date has examined the combined effect of diet and exercise on this condition.", "formality_level": "formal"},
    {"template": "There is a notable lack of research on [X]", "category": "Identifying a Gap", "subcategory": "Research Gap", "example": "There is a notable lack of research on the experiences of first-generation university students.", "formality_level": "formal"},
    {"template": "Despite its importance, [X] remains poorly understood", "category": "Identifying a Gap", "subcategory": "Knowledge Gap", "example": "Despite its importance, the mechanism of drug resistance remains poorly understood.", "formality_level": "formal"},
    {"template": "The existing literature on [X] has several limitations", "category": "Identifying a Gap", "subcategory": "Limitations", "example": "The existing literature on remote working has several limitations, including small sample sizes.", "formality_level": "formal"},
    {"template": "Few researchers have addressed the problem of [X]", "category": "Identifying a Gap", "subcategory": "Research Gap", "example": "Few researchers have addressed the problem of data quality in large-scale surveys.", "formality_level": "formal"},
    {"template": "While much has been written about [X], considerably less attention has been paid to [Y]", "category": "Identifying a Gap", "subcategory": "Neglected Area", "example": "While much has been written about leadership styles, considerably less attention has been paid to follower dynamics.", "formality_level": "formal"},
    {"template": "To date, there has been little agreement on [X]", "category": "Identifying a Gap", "subcategory": "Debate", "example": "To date, there has been little agreement on the optimal dosage for this medication.", "formality_level": "formal"},
    {"template": "The question of [X] has not been adequately explored", "category": "Identifying a Gap", "subcategory": "Research Gap", "example": "The question of how cultural norms influence health-seeking behaviour has not been adequately explored.", "formality_level": "formal"},
    {"template": "A key limitation of existing research is that [X]", "category": "Identifying a Gap", "subcategory": "Limitations", "example": "A key limitation of existing research is that most studies rely on self-reported data.", "formality_level": "formal"},

    # ── Defining Terms ───────────────────────────────────────────────
    {"template": "The term [X] refers to [Y]", "category": "Defining Terms", "subcategory": "Direct Definition", "example": "The term 'resilience' refers to the ability to recover from adversity.", "formality_level": "formal"},
    {"template": "[X] can be defined as [Y]", "category": "Defining Terms", "subcategory": "Direct Definition", "example": "Social capital can be defined as the networks and relationships that facilitate collective action.", "formality_level": "formal"},
    {"template": "For the purposes of this study, [X] is understood as [Y]", "category": "Defining Terms", "subcategory": "Operational Definition", "example": "For the purposes of this study, 'engagement' is understood as active participation in learning activities.", "formality_level": "formal"},
    {"template": "In the context of [X], [Y] is used to describe [Z]", "category": "Defining Terms", "subcategory": "Contextual Definition", "example": "In the context of education, 'scaffolding' is used to describe temporary support structures.", "formality_level": "formal"},
    {"template": "[X] is generally understood to mean [Y]", "category": "Defining Terms", "subcategory": "Common Understanding", "example": "Sustainability is generally understood to mean meeting present needs without compromising future generations.", "formality_level": "formal"},
    {"template": "The concept of [X] has been variously defined, but here it denotes [Y]", "category": "Defining Terms", "subcategory": "Stipulative Definition", "example": "The concept of well-being has been variously defined, but here it denotes subjective life satisfaction.", "formality_level": "formal"},
    {"template": "[X] is a broad term encompassing [Y]", "category": "Defining Terms", "subcategory": "Scope Definition", "example": "Digital literacy is a broad term encompassing the skills needed to navigate online environments.", "formality_level": "formal"},
    {"template": "Throughout this paper, [X] will be used to refer to [Y]", "category": "Defining Terms", "subcategory": "Operational Definition", "example": "Throughout this paper, 'intervention' will be used to refer to the structured programme.", "formality_level": "formal"},
    {"template": "A distinction should be drawn between [X] and [Y]", "category": "Defining Terms", "subcategory": "Distinction", "example": "A distinction should be drawn between correlation and causation.", "formality_level": "formal"},
    {"template": "[X], as used in this study, encompasses [Y]", "category": "Defining Terms", "subcategory": "Operational Definition", "example": "Academic success, as used in this study, encompasses both grades and degree completion.", "formality_level": "formal"},

    # ── Describing Methodology ───────────────────────────────────────
    {"template": "Data were collected using [X]", "category": "Describing Methodology", "subcategory": "Data Collection", "example": "Data were collected using semi-structured interviews with 30 participants.", "formality_level": "formal"},
    {"template": "A [X] approach was adopted to [Y]", "category": "Describing Methodology", "subcategory": "Research Design", "example": "A mixed-methods approach was adopted to capture both quantitative and qualitative dimensions.", "formality_level": "formal"},
    {"template": "Participants were recruited through [X]", "category": "Describing Methodology", "subcategory": "Sampling", "example": "Participants were recruited through purposive sampling from three urban hospitals.", "formality_level": "formal"},
    {"template": "The study employed a [X] design to investigate [Y]", "category": "Describing Methodology", "subcategory": "Research Design", "example": "The study employed a randomised controlled trial design to investigate treatment efficacy.", "formality_level": "formal"},
    {"template": "Analysis was conducted using [X]", "category": "Describing Methodology", "subcategory": "Analysis", "example": "Analysis was conducted using thematic analysis as described by Braun and Clarke.", "formality_level": "formal"},
    {"template": "The sample consisted of [X] participants who [Y]", "category": "Describing Methodology", "subcategory": "Sampling", "example": "The sample consisted of 200 participants who had at least five years of teaching experience.", "formality_level": "formal"},
    {"template": "To control for [X], the study incorporated [Y]", "category": "Describing Methodology", "subcategory": "Controls", "example": "To control for confounding variables, the study incorporated a matched-pairs design.", "formality_level": "formal"},
    {"template": "Ethical approval was obtained from [X]", "category": "Describing Methodology", "subcategory": "Ethics", "example": "Ethical approval was obtained from the University Research Ethics Committee.", "formality_level": "formal"},
    {"template": "[X] was measured using [Y]", "category": "Describing Methodology", "subcategory": "Measurement", "example": "Anxiety was measured using the Generalised Anxiety Disorder 7-item scale.", "formality_level": "formal"},
    {"template": "The data were analysed using [X] to determine [Y]", "category": "Describing Methodology", "subcategory": "Analysis", "example": "The data were analysed using regression analysis to determine the predictors of attrition.", "formality_level": "formal"},

    # ── Presenting Results ───────────────────────────────────────────
    {"template": "The results indicate that [X]", "category": "Presenting Results", "subcategory": "Key Finding", "example": "The results indicate that the intervention group showed significantly greater improvement.", "formality_level": "formal"},
    {"template": "As shown in [X], there was a significant [Y]", "category": "Presenting Results", "subcategory": "Referencing Data", "example": "As shown in Table 2, there was a significant correlation between the two variables.", "formality_level": "formal"},
    {"template": "A statistically significant difference was found between [X] and [Y]", "category": "Presenting Results", "subcategory": "Statistical Finding", "example": "A statistically significant difference was found between the control and experimental groups.", "formality_level": "formal"},
    {"template": "The most striking result to emerge from the data is that [X]", "category": "Presenting Results", "subcategory": "Notable Finding", "example": "The most striking result to emerge from the data is that older participants outperformed younger ones.", "formality_level": "formal"},
    {"template": "No significant difference was found between [X] and [Y]", "category": "Presenting Results", "subcategory": "Null Finding", "example": "No significant difference was found between male and female responses.", "formality_level": "formal"},
    {"template": "[X] was found to be positively correlated with [Y]", "category": "Presenting Results", "subcategory": "Correlation", "example": "Hours of practice was found to be positively correlated with performance scores.", "formality_level": "formal"},
    {"template": "The analysis revealed that [X]", "category": "Presenting Results", "subcategory": "Key Finding", "example": "The analysis revealed that three distinct themes emerged from the interview data.", "formality_level": "formal"},
    {"template": "Closer inspection of the data shows [X]", "category": "Presenting Results", "subcategory": "Detailed Finding", "example": "Closer inspection of the data shows a non-linear relationship between dose and response.", "formality_level": "formal"},
    {"template": "On average, participants [X] compared to [Y]", "category": "Presenting Results", "subcategory": "Comparative Finding", "example": "On average, participants in the treatment group scored 15% higher compared to the control group.", "formality_level": "formal"},
    {"template": "The data suggest a trend towards [X]", "category": "Presenting Results", "subcategory": "Trend", "example": "The data suggest a trend towards increasing adoption of digital tools among older adults.", "formality_level": "formal"},

    # ── Discussing Implications ──────────────────────────────────────
    {"template": "These findings suggest that [X]", "category": "Discussing Implications", "subcategory": "Interpretation", "example": "These findings suggest that early intervention is crucial for optimal outcomes.", "formality_level": "formal"},
    {"template": "One possible explanation for [X] is that [Y]", "category": "Discussing Implications", "subcategory": "Explanation", "example": "One possible explanation for the low response rate is that participants experienced survey fatigue.", "formality_level": "formal"},
    {"template": "This result is consistent with [X] who found that [Y]", "category": "Discussing Implications", "subcategory": "Agreement", "example": "This result is consistent with Smith (2020) who found that feedback improves retention.", "formality_level": "formal"},
    {"template": "The findings have important implications for [X]", "category": "Discussing Implications", "subcategory": "Practical Implications", "example": "The findings have important implications for the design of public health campaigns.", "formality_level": "formal"},
    {"template": "A possible reason for [X] might be that [Y]", "category": "Discussing Implications", "subcategory": "Explanation", "example": "A possible reason for the discrepancy might be that different measurement tools were used.", "formality_level": "formal"},
    {"template": "Contrary to expectations, [X] was found to [Y]", "category": "Discussing Implications", "subcategory": "Unexpected Finding", "example": "Contrary to expectations, increased funding was found to have no effect on student outcomes.", "formality_level": "formal"},
    {"template": "These results further support the idea that [X]", "category": "Discussing Implications", "subcategory": "Confirmation", "example": "These results further support the idea that collaborative learning enhances critical thinking.", "formality_level": "formal"},
    {"template": "This finding has significant implications for the understanding of [X]", "category": "Discussing Implications", "subcategory": "Theoretical Implications", "example": "This finding has significant implications for the understanding of language acquisition.", "formality_level": "formal"},
    {"template": "The observed increase in [X] could be attributed to [Y]", "category": "Discussing Implications", "subcategory": "Attribution", "example": "The observed increase in engagement could be attributed to the gamification elements.", "formality_level": "formal"},
    {"template": "An implication of this is the possibility that [X]", "category": "Discussing Implications", "subcategory": "Speculation", "example": "An implication of this is the possibility that the effect is mediated by motivation levels.", "formality_level": "formal"},

    # ── Hedging & Qualifying ─────────────────────────────────────────
    {"template": "It is possible that [X] may [Y]", "category": "Hedging & Qualifying", "subcategory": "Possibility", "example": "It is possible that the small sample size may have influenced the results.", "formality_level": "formal"},
    {"template": "This suggests that [X], although [Y]", "category": "Hedging & Qualifying", "subcategory": "Qualification", "example": "This suggests that the treatment is effective, although further trials are needed.", "formality_level": "formal"},
    {"template": "The evidence seems to indicate that [X]", "category": "Hedging & Qualifying", "subcategory": "Tentative Claim", "example": "The evidence seems to indicate that the programme has a modest positive effect.", "formality_level": "formal"},
    {"template": "It could be argued that [X]", "category": "Hedging & Qualifying", "subcategory": "Tentative Claim", "example": "It could be argued that the benefits outweigh the potential risks.", "formality_level": "formal"},
    {"template": "This interpretation should be treated with caution because [X]", "category": "Hedging & Qualifying", "subcategory": "Caution", "example": "This interpretation should be treated with caution because the study was cross-sectional.", "formality_level": "formal"},
    {"template": "While the results are promising, [X] should be considered", "category": "Hedging & Qualifying", "subcategory": "Qualification", "example": "While the results are promising, the lack of a control group should be considered.", "formality_level": "formal"},
    {"template": "It appears that [X], though further research is needed to confirm [Y]", "category": "Hedging & Qualifying", "subcategory": "Tentative Claim", "example": "It appears that the effect is dose-dependent, though further research is needed to confirm this.", "formality_level": "formal"},
    {"template": "The findings tentatively suggest that [X]", "category": "Hedging & Qualifying", "subcategory": "Tentative Claim", "example": "The findings tentatively suggest that the association may be causal.", "formality_level": "formal"},
    {"template": "There is some evidence to suggest that [X], but [Y]", "category": "Hedging & Qualifying", "subcategory": "Balanced Claim", "example": "There is some evidence to suggest that the approach works, but the sample was limited.", "formality_level": "formal"},
    {"template": "[X] may be partly explained by [Y]", "category": "Hedging & Qualifying", "subcategory": "Partial Explanation", "example": "The variation in results may be partly explained by differences in implementation.", "formality_level": "formal"},

    # ── Comparing & Contrasting ──────────────────────────────────────
    {"template": "In contrast to [X], [Y] shows that [Z]", "category": "Comparing & Contrasting", "subcategory": "Contrast", "example": "In contrast to earlier findings, this study shows that the effect is not significant.", "formality_level": "formal"},
    {"template": "While [X], it is also true that [Y]", "category": "Comparing & Contrasting", "subcategory": "Balance", "example": "While the method is efficient, it is also true that it sacrifices some accuracy.", "formality_level": "formal"},
    {"template": "Unlike [X], [Y] demonstrates that [Z]", "category": "Comparing & Contrasting", "subcategory": "Contrast", "example": "Unlike traditional approaches, the new framework demonstrates that flexibility improves outcomes.", "formality_level": "formal"},
    {"template": "Similarly, [X] found that [Y]", "category": "Comparing & Contrasting", "subcategory": "Similarity", "example": "Similarly, Johnson (2019) found that student engagement increased with active learning.", "formality_level": "formal"},
    {"template": "[X] differs from [Y] in that [Z]", "category": "Comparing & Contrasting", "subcategory": "Distinction", "example": "This approach differs from previous methods in that it accounts for cultural variables.", "formality_level": "formal"},
    {"template": "Both [X] and [Y] share the common feature of [Z]", "category": "Comparing & Contrasting", "subcategory": "Similarity", "example": "Both qualitative and quantitative methods share the common feature of systematic data collection.", "formality_level": "formal"},
    {"template": "On the one hand [X], while on the other [Y]", "category": "Comparing & Contrasting", "subcategory": "Balance", "example": "On the one hand the policy reduces costs, while on the other it limits patient choice.", "formality_level": "formal"},
    {"template": "Whereas [X], [Y] suggests a different pattern", "category": "Comparing & Contrasting", "subcategory": "Contrast", "example": "Whereas earlier studies reported positive outcomes, this study suggests a different pattern.", "formality_level": "formal"},
    {"template": "The key difference between [X] and [Y] is [Z]", "category": "Comparing & Contrasting", "subcategory": "Distinction", "example": "The key difference between the two models is the treatment of measurement error.", "formality_level": "formal"},
    {"template": "[X] is comparable to [Y] in terms of [Z]", "category": "Comparing & Contrasting", "subcategory": "Similarity", "example": "The new technique is comparable to the gold standard in terms of diagnostic accuracy.", "formality_level": "formal"},

    # ── Concluding ───────────────────────────────────────────────────
    {"template": "Taken together, these findings suggest that [X]", "category": "Concluding", "subcategory": "Summary", "example": "Taken together, these findings suggest that the programme is both effective and scalable.", "formality_level": "formal"},
    {"template": "In conclusion, this study has shown that [X]", "category": "Concluding", "subcategory": "Summary", "example": "In conclusion, this study has shown that targeted feedback significantly improves writing quality.", "formality_level": "formal"},
    {"template": "The findings of this study have a number of practical implications for [X]", "category": "Concluding", "subcategory": "Implications", "example": "The findings of this study have a number of practical implications for teacher training.", "formality_level": "formal"},
    {"template": "Further research is needed to [X]", "category": "Concluding", "subcategory": "Future Work", "example": "Further research is needed to determine the long-term sustainability of these outcomes.", "formality_level": "formal"},
    {"template": "This study contributes to the existing body of knowledge on [X] by [Y]", "category": "Concluding", "subcategory": "Contribution", "example": "This study contributes to the existing body of knowledge on migration by offering a longitudinal perspective.", "formality_level": "formal"},
    {"template": "The current study adds to the growing literature on [X]", "category": "Concluding", "subcategory": "Contribution", "example": "The current study adds to the growing literature on artificial intelligence in healthcare.", "formality_level": "formal"},
    {"template": "Notwithstanding its limitations, this study offers valuable insights into [X]", "category": "Concluding", "subcategory": "Balanced Conclusion", "example": "Notwithstanding its limitations, this study offers valuable insights into classroom dynamics.", "formality_level": "formal"},
    {"template": "Future studies should consider [X] to further [Y]", "category": "Concluding", "subcategory": "Future Work", "example": "Future studies should consider larger sample sizes to further validate these findings.", "formality_level": "formal"},
    {"template": "Overall, the evidence presented here supports the view that [X]", "category": "Concluding", "subcategory": "Summary", "example": "Overall, the evidence presented here supports the view that prevention is more cost-effective than treatment.", "formality_level": "formal"},
    {"template": "The principal limitation of this study is [X]", "category": "Concluding", "subcategory": "Limitations", "example": "The principal limitation of this study is the reliance on a single geographical region.", "formality_level": "formal"},

    # ── General Transitions ──────────────────────────────────────────
    {"template": "Furthermore, [X]", "category": "General Transitions", "subcategory": "Addition", "example": "Furthermore, the study revealed unexpected patterns in participant behaviour.", "formality_level": "formal"},
    {"template": "In addition to [X], [Y] also [Z]", "category": "General Transitions", "subcategory": "Addition", "example": "In addition to academic gains, participants also reported improved well-being.", "formality_level": "formal"},
    {"template": "However, it should be noted that [X]", "category": "General Transitions", "subcategory": "Contrast", "example": "However, it should be noted that these results are based on a small sample.", "formality_level": "formal"},
    {"template": "Consequently, [X]", "category": "General Transitions", "subcategory": "Result", "example": "Consequently, the findings cannot be generalised to the broader population.", "formality_level": "formal"},
    {"template": "Nevertheless, [X] remains an important consideration", "category": "General Transitions", "subcategory": "Concession", "example": "Nevertheless, cost-effectiveness remains an important consideration.", "formality_level": "formal"},
    {"template": "It is important to note that [X]", "category": "General Transitions", "subcategory": "Emphasis", "example": "It is important to note that the study was conducted during the pandemic.", "formality_level": "formal"},
    {"template": "With regard to [X], it was found that [Y]", "category": "General Transitions", "subcategory": "Topic Shift", "example": "With regard to gender differences, it was found that female participants scored higher.", "formality_level": "formal"},
    {"template": "As previously mentioned, [X]", "category": "General Transitions", "subcategory": "Reference", "example": "As previously mentioned, the methodology was adapted from existing frameworks.", "formality_level": "formal"},
    {"template": "Turning now to [X], it is clear that [Y]", "category": "General Transitions", "subcategory": "Topic Shift", "example": "Turning now to the qualitative data, it is clear that participants valued peer support.", "formality_level": "formal"},
    {"template": "Having considered [X], it is now necessary to examine [Y]", "category": "General Transitions", "subcategory": "Topic Shift", "example": "Having considered the theoretical framework, it is now necessary to examine the empirical evidence.", "formality_level": "formal"},
]


def main():
    print(f"Seeding {len(PHRASES)} phrases into Supabase...")

    # Clear existing phrases first (idempotent re-runs)
    existing = supabase.table("phrases").select("id").execute()
    if existing.data:
        print(f"  Clearing {len(existing.data)} existing phrases...")
        supabase.table("phrases").delete().neq("id", 0).execute()

    # Insert in batches
    BATCH = 50
    inserted = 0
    for i in range(0, len(PHRASES), BATCH):
        batch = PHRASES[i : i + BATCH]
        result = supabase.table("phrases").insert(batch).execute()
        inserted += len(result.data)
        print(f"  Inserted {inserted}/{len(PHRASES)}")

    print(f"\nDone! {inserted} phrases seeded across {len(set(p['category'] for p in PHRASES))} categories.")


if __name__ == "__main__":
    main()

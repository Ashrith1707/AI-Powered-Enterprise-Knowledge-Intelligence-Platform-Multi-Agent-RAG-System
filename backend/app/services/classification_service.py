"""Keyword-scoring document classifier. Deterministic, explainable, no LLM cost."""

CATEGORY_KEYWORDS = {
    "finance": ["invoice", "payment", "budget", "revenue", "expense", "tax",
                "balance", "audit", "salary", "profit", "loss", "financial"],
    "legal": ["agreement", "contract", "clause", "party", "liability", "hereby",
              "jurisdiction", "confidential", "terms", "warranty", "indemnity"],
    "hr": ["employee", "recruitment", "leave", "policy", "onboarding", "payroll",
           "appraisal", "resignation", "attendance", "benefits"],
    "technical": ["architecture", "api", "database", "deployment", "server",
                  "software", "algorithm", "requirements", "design", "module"],
    "report": ["quarterly", "annual", "summary", "analysis", "findings",
               "metrics", "overview", "performance", "results"],
}


class ClassificationService:
    def classify(self, pages: list[dict], keywords: list[str]) -> str:
        text = (" ".join(p["text"] for p in pages) + " " + " ".join(keywords)).lower()
        scores = {
            category: sum(text.count(kw) for kw in kws)
            for category, kws in CATEGORY_KEYWORDS.items()
        }
        best_category, best_score = max(scores.items(), key=lambda kv: kv[1])
        return best_category if best_score >= 3 else "general"

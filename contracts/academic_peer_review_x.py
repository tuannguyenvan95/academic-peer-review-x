# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
from dataclasses import dataclass
import json

if not hasattr(gl, "UserError"):
    try:
        gl.UserError = gl.vm.UserError
    except Exception:
        pass


def _addr_str(addr: Address) -> str:
    """Safely format an Address instance into a lowercase hex string."""
    try:
        return addr.as_hex.lower()
    except Exception:
        return str(addr).lower()


def _get_sender() -> Address:
    """Safely obtain transaction sender across GenVM runtime versions."""
    try:
        return gl.message.sender
    except Exception:
        try:
            return gl.message.sender_address
        except Exception:
            raise gl.UserError("Cannot resolve sender address.")


def _safe_transfer(recipient: Address, amount: bigint) -> None:
    """Safely disburse native GEN to an address using official GenLayer SDK pattern."""
    if amount <= bigint(0):
        return
    gl.get_contract_at(recipient).emit_transfer(value=u256(int(amount)))


DEFAULT_ACADEMIC_DOMAINS = (
    "arxiv.org",
    "www.arxiv.org",
    "nature.com",
    "www.nature.com",
    "sciencedirect.com",
    "www.sciencedirect.com",
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "doi.org",
    "www.doi.org",
    "biorxiv.org",
    "www.biorxiv.org",
    "ieee.org",
    "ieeexplore.ieee.org",
    "mock-science.genlayer.com",
)


def _parse_url_host(raw_url: str) -> str:
    """Extract and validate normalized hostname from URL."""
    clean = raw_url.strip()
    if "?" in clean:
        clean = clean.split("?")[0]
    if "#" in clean:
        clean = clean.split("#")[0]
    clean = clean.strip()

    if clean.startswith("https://"):
        rest = clean[8:]
    elif clean.startswith("http://"):
        rest = clean[7:]
    else:
        raise gl.UserError("URL must begin with http:// or https://")

    host = rest.split("/", 1)[0].strip().lower()
    if ":" in host:
        host = host.split(":")[0].strip()
    if not host:
        raise gl.UserError("Invalid URL: missing host")
    return host


@allow_storage
@dataclass
class ResearchGrant:
    grant_id: str
    funder: Address
    researcher: Address
    research_topic: str
    required_keywords: str     # Comma-separated scientific topics/hypotheses
    paper_doi_or_id: str       # Unique DOI or arXiv identifier
    publication_url: str       # Canonical publication page
    escrow_amount: bigint
    status: str                # "CREATED", "SUBMITTED", "SETTLED", "CANCELLED"
    tier: str                  # "MAJOR_BREAKTHROUGH", "VALIDATED_CONTRIBUTION", "REJECTED", "CANCELLED", "NONE"
    payout_percentage: bigint  # 100, 60, 0
    researcher_payout: bigint
    funder_refund: bigint
    reason: str                # AI Jury rationale
    deadline: bigint           # Expiration timestamp for paper submission
    created_at: bigint
    resolved_at: bigint


class Contract(gl.Contract):
    """
    AcademicPeerReviewX: Decentralized Research Grant & Peer-Review Publication Arbiter
    Track: Future of Work / Public Goods
    """
    owner: Address
    grant_count: bigint
    grants: TreeMap[str, ResearchGrant]
    custom_allowed_domains: TreeMap[str, bool]

    def __init__(self):
        # GenVM automatically initializes TreeMap storage fields to empty.
        self.owner = _get_sender()
        self.grant_count = bigint(0)

    def _get_current_timestamp(self) -> bigint:
        """Derive trusted deterministic execution timestamp from GenLayer transaction context."""
        try:
            from datetime import datetime
            dt_raw = getattr(gl.message, "datetime", None)
            if dt_raw is None and hasattr(gl, "message_raw") and isinstance(gl.message_raw, dict):
                dt_raw = gl.message_raw.get("datetime")
            if dt_raw:
                dt_str = str(dt_raw).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(dt_str)
                ts = int(dt.timestamp())
                if ts > 0:
                    return bigint(ts)
        except Exception:
            pass

        try:
            if hasattr(gl, "block") and hasattr(gl.block, "timestamp"):
                ts = int(gl.block.timestamp)
                if ts > 0:
                    return bigint(ts)
        except Exception:
            pass

        return bigint(0)

    def _parse_llm_json(self, text: str) -> dict:
        """Safely parse LLM responses, stripping markdown wrappers if present."""
        try:
            cleaned = str(text).strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())
        except Exception as e:
            return {
                "tier": "REJECTED",
                "confidence": 0,
                "reason": f"Failed to parse LLM JSON: {str(e)[:100]}"
            }

    @gl.public.write
    def add_allowed_academic_domain(self, domain: str) -> None:
        """Owner can add trusted academic publisher domains."""
        if _addr_str(_get_sender()) != _addr_str(self.owner):
            raise gl.UserError("Only contract owner can add allowed domains.")
        clean = domain.strip().lower()
        if len(clean) < 3:
            raise gl.UserError("Invalid domain name.")
        self.custom_allowed_domains[clean] = True

    @gl.public.write
    def remove_allowed_academic_domain(self, domain: str) -> None:
        """Owner can remove custom allowed domain."""
        if _addr_str(_get_sender()) != _addr_str(self.owner):
            raise gl.UserError("Only contract owner can remove allowed domains.")
        clean = domain.strip().lower()
        self.custom_allowed_domains[clean] = False

    @gl.public.view
    def is_domain_allowed(self, domain: str) -> bool:
        """Check if an academic domain is whitelisted."""
        clean = domain.strip().lower()
        if clean in DEFAULT_ACADEMIC_DOMAINS:
            return True
        return clean in self.custom_allowed_domains and self.custom_allowed_domains[clean]

    @gl.public.write.payable
    def create_research_grant(
        self,
        researcher: Address,
        research_topic: str,
        required_keywords: str,
        paper_doi_or_id: str,
        deadline_timestamp: int
    ) -> str:
        """
        DeSci Funder creates an escrow grant for a scientific publication with a strict deadline.
        """
        deposit = bigint(gl.message.value)
        if deposit <= bigint(0):
            raise gl.UserError("Grant funding must be greater than 0 GEN.")

        clean_topic = research_topic.strip()
        clean_kw = required_keywords.strip()
        clean_doi = paper_doi_or_id.strip()

        if len(clean_topic) < 10:
            raise gl.UserError("research_topic must be comprehensive (min 10 chars).")
        if len(clean_doi) < 4:
            raise gl.UserError("paper_doi_or_id must be a valid identifier.")

        if _addr_str(_get_sender()) == _addr_str(researcher):
            raise gl.UserError("Funder cannot grant to self.")

        dl = bigint(deadline_timestamp)
        if dl <= bigint(0):
            raise gl.UserError("deadline_timestamp must be greater than 0.")

        now_ts = self._get_current_timestamp()
        if now_ts > bigint(0) and dl <= now_ts:
            raise gl.UserError("deadline_timestamp must be in the future.")

        self.grant_count += bigint(1)
        gid = str(self.grant_count)

        self.grants[gid] = ResearchGrant(
            grant_id=gid,
            funder=_get_sender(),
            researcher=researcher,
            research_topic=clean_topic,
            required_keywords=clean_kw,
            paper_doi_or_id=clean_doi,
            publication_url="",
            escrow_amount=deposit,
            status="CREATED",
            tier="NONE",
            payout_percentage=bigint(0),
            researcher_payout=bigint(0),
            funder_refund=bigint(0),
            reason="Grant locked. Awaiting publication link from researcher.",
            deadline=dl,
            created_at=self.grant_count,
            resolved_at=bigint(0)
        )

        return gid

    @gl.public.write
    def submit_publication(self, grant_id: str, publication_url: str) -> None:
        """
        Researcher submits the authoritative published article URL before deadline.
        """
        if grant_id not in self.grants:
            raise gl.UserError("Grant not found.")

        grant = self.grants[grant_id]
        if _addr_str(_get_sender()) != _addr_str(grant.researcher):
            raise gl.UserError("Only designated researcher can submit publication.")

        if grant.status == "SETTLED":
            raise gl.UserError("Grant already settled.")
        if grant.status == "CANCELLED":
            raise gl.UserError("Grant is cancelled.")

        now_ts = self._get_current_timestamp()
        if now_ts > bigint(0) and now_ts > grant.deadline:
            raise gl.UserError("Grant submission deadline has passed.")

        clean_url = publication_url.strip()
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            raise gl.UserError("publication_url must begin with http:// or https://")

        # Canonical Host Validation
        host = _parse_url_host(clean_url)
        is_allowed = (host in DEFAULT_ACADEMIC_DOMAINS) or (
            host in self.custom_allowed_domains and self.custom_allowed_domains[host]
        )
        if not is_allowed:
            raise gl.UserError(f"Academic publisher '{host}' is not in the allowed domain whitelist.")

        # Canonical Identifier Binding (Prevent URL spoofing / Cross-grant replay)
        if grant.paper_doi_or_id.lower() not in clean_url.lower():
            raise gl.UserError(f"Publication URL must canonically contain the specified DOI/ID '{grant.paper_doi_or_id}'.")

        grant.publication_url = clean_url
        grant.status = "SUBMITTED"
        self.grants[grant_id] = grant

    @gl.public.write
    def cancel_expired_grant(self, grant_id: str) -> None:
        """
        Safe Funder Recovery Path:
        If researcher fails to submit published paper before deadline, funder recovers 100% refund.
        """
        if grant_id not in self.grants:
            raise gl.UserError("Grant not found.")

        grant = self.grants[grant_id]
        if _addr_str(_get_sender()) != _addr_str(grant.funder):
            raise gl.UserError("Only grant funder can cancel unsubmitted grant.")

        if grant.status == "SETTLED":
            raise gl.UserError("Grant is already settled.")
        if grant.status == "CANCELLED":
            raise gl.UserError("Grant is already cancelled.")
        if grant.status == "SUBMITTED":
            raise gl.UserError("Cannot cancel grant once paper has been submitted.")

        now_ts = self._get_current_timestamp()
        if now_ts > bigint(0) and now_ts <= grant.deadline:
            raise gl.UserError("Grant deadline has not passed yet.")

        refund_amt = grant.escrow_amount

        grant.status = "CANCELLED"
        grant.tier = "CANCELLED"
        grant.payout_percentage = bigint(0)
        grant.researcher_payout = bigint(0)
        grant.funder_refund = refund_amt
        grant.reason = "Grant cancelled by funder after researcher missed submission deadline."
        grant.resolved_at = self.grant_count
        self.grants[grant_id] = grant

        if refund_amt > bigint(0):
            _safe_transfer(grant.funder, refund_amt)

    @gl.public.write
    def adjudicate_grant(self, grant_id: str) -> None:
        """
        Validators inspect paper metadata, peer-review status, and topic alignment,
        then disburse funds deterministically according to discrete tiers.
        """
        if grant_id not in self.grants:
            raise gl.UserError("Grant not found.")

        grant = self.grants[grant_id]
        if grant.status == "CANCELLED":
            raise gl.UserError("Cannot adjudicate a cancelled grant.")
        if grant.status != "SUBMITTED":
            raise gl.UserError("Paper has not been submitted or already settled.")

        if not grant.publication_url:
            raise gl.UserError("Publication URL is missing.")

        topic_local = str(grant.research_topic)
        kw_local = str(grant.required_keywords)
        doi_local = str(grant.paper_doi_or_id)
        pub_url_local = str(grant.publication_url)

        def leader_fn():
            web_content = ""
            try:
                res = gl.nondet.web.render(pub_url_local, mode="text")
                if hasattr(res, "content"):
                    web_content = res.content
                elif isinstance(res, dict) and "body" in res:
                    web_content = res["body"]
                else:
                    web_content = str(res)
            except Exception:
                web_content = ""

            lower_web = web_content[:500].lower() if web_content else ""
            if len(web_content.strip()) < 15 or "404 not found" in lower_web or "access denied" in lower_web:
                return {
                    "tier": "REJECTED",
                    "confidence": 100,
                    "reason": "Paper URL returned 404, offline, or inaccessible content."
                }

            snippet = web_content[:4000]

            prompt = f"""You are an Impartial Academic Peer-Review Jury on the GenLayer network.
Evaluate the published scientific article against the agreed research grant scope.

GRANT TOPIC:
\"\"\"
{topic_local}
\"\"\"

REQUIRED KEYWORDS / HYPOTHESES:
\"\"\"
{kw_local}
\"\"\"

VERIFIED IDENTIFIER: {doi_local}
SOURCE URL: {pub_url_local}

OBSERVED ARTICLE CONTENT:
\"\"\"
{snippet}
\"\"\"

PEER-REVIEW CLASSIFICATION TIERS:
- "MAJOR_BREAKTHROUGH": 100% payout. The paper is peer-reviewed/accepted, directly addresses the topic, rigorously demonstrates results, and fulfills all hypotheses.
- "VALIDATED_CONTRIBUTION": 60% payout. Legitimate scientific preprint/paper, partially validates hypotheses with sound methodology, but lacks peer-review stamp or has minor topic drift.
- "REJECTED": 0% payout. Off-topic, predatory publication, retracted, missing identifier, plagiarism, or fails basic scientific validity.

OUTPUT FORMAT:
Respond ONLY with a VALID JSON object (no markdown, no backticks):
{{
  "tier": "MAJOR_BREAKTHROUGH" | "VALIDATED_CONTRIBUTION" | "REJECTED",
  "confidence": <integer from 0 to 100>,
  "reason": "<concise breakdown max 220 characters>"
}}"""

            try:
                raw_res = gl.nondet.exec_prompt(prompt, response_format="json")
                parsed = None
                if isinstance(raw_res, dict):
                    parsed = raw_res
                elif hasattr(raw_res, "content") and isinstance(raw_res.content, dict):
                    parsed = raw_res.content
                else:
                    text = raw_res.content if hasattr(raw_res, "content") else str(raw_res)
                    cleaned = str(text).strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    elif cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    parsed = json.loads(cleaned.strip())

                tier_candidate = str(parsed.get("tier", "REJECTED")).strip().upper()
                valid_tiers = ("MAJOR_BREAKTHROUGH", "VALIDATED_CONTRIBUTION", "REJECTED")
                if tier_candidate not in valid_tiers:
                    tier_candidate = "REJECTED"

                try:
                    conf = int(parsed.get("confidence", 0))
                    conf = max(0, min(100, conf))
                except Exception:
                    conf = 50

                reason_str = str(parsed.get("reason", "Article audited by academic jury."))[:220]

                return {
                    "tier": tier_candidate,
                    "confidence": conf,
                    "reason": reason_str
                }
            except Exception as e:
                return {
                    "tier": "REJECTED",
                    "confidence": 0,
                    "reason": f"Evaluation error: {str(e)[:100]}"
                }

        def validator_fn(leader_res) -> bool:
            if not isinstance(leader_res, gl.vm.Return):
                return False
            leader = leader_res.calldata
            if not isinstance(leader, dict) or "tier" not in leader:
                return False

            valid_tiers = ("MAJOR_BREAKTHROUGH", "VALIDATED_CONTRIBUTION", "REJECTED")
            l_tier = str(leader.get("tier", "")).strip().upper()
            if l_tier not in valid_tiers:
                return False

            mine = leader_fn()
            m_tier = str(mine.get("tier", "")).strip().upper()

            # DISCRETE EQUIVALENCE: 100% agreement on exact discrete research tier
            return l_tier == m_tier

        adjudication_res = gl.vm.run_nondet(leader_fn, validator_fn)
        if isinstance(adjudication_res, dict):
            final_res = adjudication_res
        else:
            final_res = self._parse_llm_json(str(adjudication_res))

        tier = str(final_res.get("tier", "REJECTED")).strip().upper()
        valid_tiers = ("MAJOR_BREAKTHROUGH", "VALIDATED_CONTRIBUTION", "REJECTED")
        if tier not in valid_tiers:
            tier = "REJECTED"

        reason = str(final_res.get("reason", "Consensus concluded."))

        pct = bigint(0)
        if tier == "MAJOR_BREAKTHROUGH":
            pct = bigint(100)
        elif tier == "VALIDATED_CONTRIBUTION":
            pct = bigint(60)
        else:
            pct = bigint(0)

        escrow_total = grant.escrow_amount
        researcher_share = (escrow_total * pct) // bigint(100)
        funder_refund = escrow_total - researcher_share

        grant.status = "SETTLED"
        grant.tier = tier
        grant.payout_percentage = pct
        grant.researcher_payout = researcher_share
        grant.funder_refund = funder_refund
        grant.reason = reason
        grant.resolved_at = self.grant_count
        self.grants[grant_id] = grant

        if researcher_share > bigint(0):
            _safe_transfer(grant.researcher, researcher_share)

        if funder_refund > bigint(0):
            _safe_transfer(grant.funder, funder_refund)

    @gl.public.view
    def get_grant(self, grant_id: str) -> str:
        """Retrieve details of a research grant as a JSON string."""
        if grant_id not in self.grants:
            raise gl.UserError("Grant not found.")
        g = self.grants[grant_id]
        return json.dumps({
            "grant_id": g.grant_id,
            "funder": _addr_str(g.funder),
            "researcher": _addr_str(g.researcher),
            "research_topic": g.research_topic,
            "required_keywords": g.required_keywords,
            "paper_doi_or_id": g.paper_doi_or_id,
            "publication_url": g.publication_url,
            "escrow_amount": str(g.escrow_amount),
            "status": g.status,
            "tier": g.tier,
            "payout_percentage": str(g.payout_percentage),
            "researcher_payout": str(g.researcher_payout),
            "funder_refund": str(g.funder_refund),
            "reason": g.reason,
            "deadline": str(g.deadline),
            "created_at": str(g.created_at),
            "resolved_at": str(g.resolved_at)
        })

    @gl.public.view
    def get_current_time(self) -> int:
        """Retrieve current contract execution timestamp."""
        return int(str(self._get_current_timestamp()))

    @gl.public.view
    def get_grant_count(self) -> int:
        return int(self.grant_count)

    @gl.public.view
    def get_owner(self) -> str:
        return _addr_str(self.owner)

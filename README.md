# AcademicPeerReviewX — Decentralized Research Grant & Peer-Review Publication Arbiter

> **Track:** Future of Work / Public Goods / DeSci (Decentralized Science)  
> **Network:** GenLayer studionet (Chain ID: `61999` / `0xF1EF`)  
> **Contract Address:** `0x68eb7f11bcec867955292a3a2050eD1337CB0E8C`  
> **Target Environment:** [GenLayer Studio](https://studio.genlayer.com)  
> **Execution Engine:** GenVM / Optimistic Democracy Subjective Consensus  
> **Package / SDK:** `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`  
> **Test Suite:** 15 unit tests passing (`gltest` / `pytest`)

---

## 1. Deployment & Live Network Evidence

The `AcademicPeerReviewX` Intelligent Contract is successfully deployed on GenLayer studionet:

- **Contract Address:** `0x68eb7f11bcec867955292a3a2050eD1337CB0E8C`
- **Network:** `studionet` (Chain ID: `61999` / `0xF1EF`)
- **Explorer:** [https://explorer.genlayer.com/address/0x68eb7f11bcec867955292a3a2050eD1337CB0E8C](https://explorer.genlayer.com/address/0x68eb7f11bcec867955292a3a2050eD1337CB0E8C)
- **Studio Explorer:** [https://explorer-studio.genlayer.com/address/0x68eb7f11bcec867955292a3a2050eD1337CB0E8C](https://explorer-studio.genlayer.com/address/0x68eb7f11bcec867955292a3a2050eD1337CB0E8C)
- **Contract Source:** [`contracts/academic_peer_review_x.py`](contracts/academic_peer_review_x.py)

---

## 2. Project Overview & Architectural Highlights

`AcademicPeerReviewX` is an Intelligent Contract on GenLayer built to modernize scientific research grants, citation bounties, and peer-review escrow settlement. It replaces centralized grant committee bottlenecks and opaque funding decisions with deterministic, transparent, and AI-assisted DeSci agreements.

### Core Architectural Pillars (Upgraded v2/v3 Standards):
1. **Line 1 Magic Pragma**:
   Contract begins directly with `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }` without preliminary blank lines or unparsed comments, guaranteeing exact build dependency resolution in GenVM.
2. **Canonical Host & DOI Whitelist**:
   Validates peer-reviewed repositories against a strict academic whitelist (`arxiv.org`, `nature.com`, `sciencedirect.com`, `pubmed.ncbi.nlm.nih.gov`, `biorxiv.org`, `ieee.org`, `doi.org`, `mock-science.genlayer.com`). Contract enforces that the canonical publication URL must explicitly contain the paper's assigned DOI/identifier to prevent URL spoofing and cross-grant replay exploits.
3. **Economic Determinism on Discrete Consensus Tiers**:
   Avoids leader-dependent variance by enforcing strict agreement on discrete peer-review classification tiers:
   - **`MAJOR_BREAKTHROUGH` (100% Payout, 0% Funder Refund)**: Peer-reviewed, top-tier journal/conference accepted, comprehensively addresses grant topic and hypothesis.
   - **`VALIDATED_CONTRIBUTION` (60% Payout, 40% Funder Refund)**: Legitimate preprint/paper with sound methodology, partial hypothesis fulfillment, or preprint lacking final journal stamp.
   - **`REJECTED` (0% Payout, 100% Funder Refund)**: Off-topic, predatory publisher, unverified identifier, 404/inaccessible web source, or failed scientific criteria.
4. **Safe Funder Recovery Path (`cancel_expired_grant`)**:
   If the researcher misses the hard submission deadline, the funder can cancel the unsubmitted grant and recover 100% of escrowed funds.
5. **Runtime Safety & Anti-Crash Guards**:
   Safely addresses runtime variations:
   - Aliased `gl.UserError` fallback to `gl.vm.UserError`.
   - Sender resolution supporting `gl.message.sender` and `gl.message.sender_address`.
   - Official transfer disbursements via `gl.get_contract_at(recipient).emit_transfer(value=u256(int(amount)))`.
   - Resilient timestamp derivation from `gl.message.datetime` and `gl.block.timestamp`.

---

## 3. Worked Example: Escrow Lifecycle & Consensus

### Step A: Grant Creation & Escrow Deposit
- **Funder (Alice):** `0x2bd806c97F0e00aF1a1fC3328fA763a9269723C8`
- **Researcher (Bob):** `0x81b637d8fCD2C6da6359E6963113a1170de795e4`
- **Topic:** `"Autonomous AI Consensus in Decentralized Zero-Knowledge Systems"`
- **Keywords:** `"GenLayer, Consensus, ZK-Rollup"`
- **Paper DOI / ID:** `"10.1038/s41586-026-00001"`
- **Value Attached:** `10,000 GEN`
- **Deadline Timestamp:** `2000000000` (Unix timestamp)
- **On-chain State (`get_grant("1")`):**
  ```json
  {
    "grant_id": "1",
    "funder": "0x2bd806c97f0e00af1a1fc3328fa763a9269723c8",
    "researcher": "0x81b637d8fcd2c6da6359e6963113a1170de795e4",
    "research_topic": "Autonomous AI Consensus in Decentralized Zero-Knowledge Systems",
    "required_keywords": "GenLayer, Consensus, ZK-Rollup",
    "paper_doi_or_id": "10.1038/s41586-026-00001",
    "publication_url": "",
    "escrow_amount": "10000",
    "status": "CREATED",
    "tier": "NONE",
    "payout_percentage": "0",
    "researcher_payout": "0",
    "funder_refund": "0",
    "reason": "Grant locked. Awaiting publication link from researcher.",
    "deadline": "2000000000",
    "created_at": "1",
    "resolved_at": "0"
  }
  ```

### Step B: Publication Submission
- **Caller (Bob):** `submit_publication(grant_id="1", publication_url="https://nature.com/articles/10.1038/s41586-026-00001")`
- **Validations Enforced:**
  - Whitelist: `nature.com` is verified in default domains.
  - Identifier Check: `10.1038/s41586-026-00001` is strictly present in the URL path.
  - Status transitions to `"SUBMITTED"`.

### Step C: Non-Deterministic Adjudication & Consensus
- **Method:** `adjudicate_grant(grant_id="1")`
- **Web Retrieval:** `gl.nondet.web.render(publication_url, mode="text")` fetches article content and abstract.
- **LLM Jury Prompting:** `gl.nondet.exec_prompt(prompt, response_format="json")` analyzes peer-review status, scientific validity, and alignment with topic and keywords.
- **Discrete Consensus:** Validators enforce:
  ```python
  return l_tier == m_tier  # Discrete tier equivalence
  ```
- **Settlement:**
  - Tier evaluated: `MAJOR_BREAKTHROUGH` (100% payout).
  - Researcher receives: `10,000 GEN`.
  - Funder refund: `0 GEN`.
  - Status becomes: `"SETTLED"`.

### Step D: Safe Funder Recovery Path (Alternative)
- If Researcher Bob misses the deadline and does not submit the article:
- **Caller (Funder Alice):** `cancel_expired_grant(grant_id="1")`
- **Result:** Alice automatically receives a 100% refund (`10,000 GEN`), and the grant status is updated to `"CANCELLED"`.

---

## 4. Contract Specification

### Public Methods

| Method | Type | Access | Description |
|---|---|---|---|
| `create_research_grant` | Write, Payable | Anyone (Funder) | Locks escrowed GEN, defines topic, keywords, DOI/ID, and deadline. |
| `submit_publication` | Write | Researcher only | Submits article publication URL adhering to whitelist and DOI containment. |
| `cancel_expired_grant` | Write | Funder only | Cancels unsubmitted grant after deadline passes and refunds 100% of escrow. |
| `adjudicate_grant` | Write | Anyone (Keeper) | Triggers web rendering + LLM jury consensus to settle funds by tier. |
| `add_allowed_academic_domain` | Write | Owner only | Adds new trusted publisher domain to whitelist. |
| `remove_allowed_academic_domain`| Write | Owner only | Removes custom allowed publisher domain. |
| `is_domain_allowed` | View | Public | Checks whether domain is whitelisted. |
| `get_grant` | View | Public | Returns complete grant details as JSON string. |
| `get_grant_count` | View | Public | Returns total grants registered. |
| `get_current_time` | View | Public | Returns current execution timestamp. |
| `get_owner` | View | Public | Returns contract owner address. |

---

## 5. Verification & Testing

The project includes a comprehensive test suite executed with `gltest` and `pytest`:

```bash
pytest -v
```

### Test Coverage Summary (15 Passing Tests):
- `test_initial_state`: Verifies zero count and correct contract ownership.
- `test_grant_creation_and_lifecycle`: Full deposit and parameter validation.
- `test_grant_creation_validation_errors`: Validates minimum topic length, non-self funding, positive deposits, and valid deadlines.
- `test_submit_publication_success`: Validates canonical URL submission.
- `test_submit_publication_validation_rules`: Validates domain whitelist and anti-spoofing DOI containment.
- `test_owner_domain_whitelist_management`: Owner controls custom domains.
- `test_adjudicate_major_breakthrough_100_percent`: Full payout to researcher.
- `test_adjudicate_validated_contribution_60_percent`: 60% researcher / 40% funder split.
- `test_adjudicate_rejected_0_percent`: 100% funder refund on off-topic/predatory paper.
- `test_adjudicate_inaccessible_or_404_url`: Graceful rejection of offline content.
- `test_cannot_adjudicate_unsubmitted_or_settled_grant`: Enforces lifecycle ordering.
- `test_safe_client_recovery_path`: Funder 100% refund upon missed deadline.
- `test_cancel_expired_grant_validations`: Enforces caller authorization and deadline conditions.
- `test_cannot_adjudicate_cancelled_grant`: Prevents double spending on cancelled grants.
- `test_consensus_rejects_divergent_payout_tiers`: Ensures validator rejection on divergent discrete tier proposals.

---

## 6. Development Setup & Deployment

### Prerequisites
- Python 3.12+ or 3.13
- Node.js & GenLayer CLI (`gltest`)

### Installation
```bash
pip install -r requirements-dev.txt
```

### Run Tests
```bash
pytest -v
```

### Deploy to GenLayer Studionet / Studio
1. Open [GenLayer Studio](https://studio.genlayer.com).
2. Create contract file `contracts/academic_peer_review_x.py`.
3. Paste the contract source code.
4. Deploy using Studionet or Localnet provider.

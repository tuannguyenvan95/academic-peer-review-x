import pytest
import json
from gltest import *


def _to_hex(addr) -> str:
    """Helper to convert test address to lowercase hex."""
    if hasattr(addr, "as_hex"):
        return addr.as_hex.lower()
    if isinstance(addr, bytes):
        return "0x" + addr.hex().lower()
    return str(addr).lower()


def setup_post_message_hook(direct_vm):
    """Intercept cross-contract calls / emit_transfer to track recipient balances in tests."""
    def post_message_hook(vm, request):
        if "PostMessage" in request:
            pm = request["PostMessage"]
            dest_addr = pm["address"]
            value = int(pm.get("value", 0))
            dest_bytes = vm._to_bytes(dest_addr)
            vm._balances[dest_bytes] = vm._balances.get(dest_bytes, 0) + value
            return {"ok": None}
        if "EthSend" in request:
            es = request["EthSend"]
            dest_addr = es.get("to") or es.get("address") or es.get("recipient")
            value = int(es.get("value", 0))
            dest_bytes = vm._to_bytes(dest_addr)
            vm._balances[dest_bytes] = vm._balances.get(dest_bytes, 0) + value
            return {"ok": None}
        return None

    direct_vm._gl_call_hook = post_message_hook


@pytest.fixture
def contract(direct_deploy):
    return direct_deploy("contracts/academic_peer_review_x.py")


def test_initial_state(contract, direct_vm, direct_alice):
    """Verify clean initial state on contract deployment."""
    assert contract.get_grant_count() == 0
    assert contract.get_owner() == _to_hex(direct_vm.sender)


def test_grant_creation_and_lifecycle(contract, direct_vm, direct_alice, direct_bob):
    """1. Test funder creating grant with 10,000 GEN and valid parameters."""
    direct_vm.sender = direct_alice
    direct_vm.value = 10000

    deadline = 2000000000  # Future timestamp
    grant_id = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Autonomous AI Consensus in Decentralized Zero-Knowledge Systems",
        required_keywords="GenLayer, Consensus, ZK-Rollup",
        paper_doi_or_id="10.1038/s41586-026-00001",
        deadline_timestamp=deadline,
    )
    assert str(grant_id) == "1"
    assert contract.get_grant_count() == 1

    grant_data = json.loads(contract.get_grant(grant_id))
    assert grant_data["grant_id"] == "1"
    assert grant_data["funder"] == _to_hex(direct_alice)
    assert grant_data["researcher"] == _to_hex(direct_bob)
    assert grant_data["escrow_amount"] == "10000"
    assert grant_data["status"] == "CREATED"
    assert grant_data["tier"] == "NONE"
    assert grant_data["payout_percentage"] == "0"
    assert grant_data["researcher_payout"] == "0"
    assert grant_data["funder_refund"] == "0"
    assert grant_data["deadline"] == str(deadline)


def test_grant_creation_validation_errors(contract, direct_vm, direct_alice, direct_bob):
    """Test validation constraints on grant creation."""
    direct_vm.sender = direct_alice

    # 1. Zero funding
    direct_vm.value = 0
    with pytest.raises(Exception) as exc:
        contract.create_research_grant(
            researcher=direct_bob,
            research_topic="Autonomous AI Consensus in Decentralized Zero-Knowledge Systems",
            required_keywords="Consensus",
            paper_doi_or_id="10.1038/0001",
            deadline_timestamp=2000000000,
        )
    assert "Grant funding must be greater than 0 GEN" in str(exc.value)

    # 2. Topic too short (< 10 chars)
    direct_vm.value = 5000
    with pytest.raises(Exception) as exc:
        contract.create_research_grant(
            researcher=direct_bob,
            research_topic="Short",
            required_keywords="Consensus",
            paper_doi_or_id="10.1038/0001",
            deadline_timestamp=2000000000,
        )
    assert "research_topic must be comprehensive" in str(exc.value)

    # 3. DOI too short (< 4 chars)
    with pytest.raises(Exception) as exc:
        contract.create_research_grant(
            researcher=direct_bob,
            research_topic="Autonomous AI Consensus in Decentralized Zero-Knowledge Systems",
            required_keywords="Consensus",
            paper_doi_or_id="12",
            deadline_timestamp=2000000000,
        )
    assert "paper_doi_or_id must be a valid identifier" in str(exc.value)

    # 4. Funder cannot grant to self
    with pytest.raises(Exception) as exc:
        contract.create_research_grant(
            researcher=direct_alice,
            research_topic="Autonomous AI Consensus in Decentralized Zero-Knowledge Systems",
            required_keywords="Consensus",
            paper_doi_or_id="10.1038/0001",
            deadline_timestamp=2000000000,
        )
    assert "Funder cannot grant to self" in str(exc.value)

    # 5. Non-positive deadline
    with pytest.raises(Exception) as exc:
        contract.create_research_grant(
            researcher=direct_bob,
            research_topic="Autonomous AI Consensus in Decentralized Zero-Knowledge Systems",
            required_keywords="Consensus",
            paper_doi_or_id="10.1038/0001",
            deadline_timestamp=0,
        )
    assert "deadline_timestamp must be greater than 0" in str(exc.value)


def test_submit_publication_success(contract, direct_vm, direct_alice, direct_bob):
    """Researcher successfully submits canonical publication URL containing DOI."""
    direct_vm.sender = direct_alice
    direct_vm.value = 10000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Zero Knowledge Rollups Security Models",
        required_keywords="ZK-Rollups, Security",
        paper_doi_or_id="10.1038/s41586-026-00001",
        deadline_timestamp=2000000000,
    )

    direct_vm.sender = direct_bob
    valid_pub_url = "https://nature.com/articles/10.1038/s41586-026-00001"
    contract.submit_publication(gid, valid_pub_url)

    grant_data = json.loads(contract.get_grant(gid))
    assert grant_data["status"] == "SUBMITTED"
    assert grant_data["publication_url"] == valid_pub_url


def test_submit_publication_validation_rules(contract, direct_vm, direct_alice, direct_bob, direct_charlie):
    """Test publisher whitelist enforcement and DOI binding check."""
    direct_vm.sender = direct_alice
    direct_vm.value = 10000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Decentralized Zero Knowledge Provers",
        required_keywords="ZK, SNARK",
        paper_doi_or_id="10.48550/arxiv.2401.99999",
        deadline_timestamp=2000000000,
    )

    # 1. Non-researcher cannot submit
    direct_vm.sender = direct_charlie
    with pytest.raises(Exception) as exc:
        contract.submit_publication(gid, "https://arxiv.org/abs/10.48550/arxiv.2401.99999")
    assert "Only designated researcher can submit publication" in str(exc.value)

    # 2. Non-whitelisted domain
    direct_vm.sender = direct_bob
    with pytest.raises(Exception) as exc:
        contract.submit_publication(gid, "https://untrusted-blog.xyz/papers/10.48550/arxiv.2401.99999")
    assert "not in the allowed domain whitelist" in str(exc.value)

    # 3. Whitelisted domain but missing DOI/ID in URL (Anti-spoofing)
    with pytest.raises(Exception) as exc:
        contract.submit_publication(gid, "https://arxiv.org/abs/unrelated-paper-id")
    assert "Publication URL must canonically contain the specified DOI/ID" in str(exc.value)

    # 4. Invalid protocol
    with pytest.raises(Exception) as exc:
        contract.submit_publication(gid, "ftp://arxiv.org/10.48550/arxiv.2401.99999")
    assert "publication_url must begin with http:// or https://" in str(exc.value)


def test_owner_domain_whitelist_management(contract, direct_vm, direct_alice, direct_bob):
    """Owner can add and remove custom allowed academic publisher domains."""
    owner_addr = contract.get_owner()
    direct_vm.sender = direct_deployer = direct_vm.sender  # owner from deploy

    assert contract.is_domain_allowed("arxiv.org") is True
    assert contract.is_domain_allowed("springer.com") is False

    # Owner adds springer.com
    contract.add_allowed_academic_domain("springer.com")
    assert contract.is_domain_allowed("springer.com") is True

    # Non-owner cannot add
    direct_vm.sender = direct_bob
    with pytest.raises(Exception) as exc:
        contract.add_allowed_academic_domain("mdpi.com")
    assert "Only contract owner can add allowed domains" in str(exc.value)

    # Owner removes springer.com
    direct_vm.sender = direct_deployer
    contract.remove_allowed_academic_domain("springer.com")
    assert contract.is_domain_allowed("springer.com") is False


def test_adjudicate_major_breakthrough_100_percent(contract, direct_vm, direct_alice, direct_bob):
    """
    Scenario 1: MAJOR_BREAKTHROUGH
    AI jury verifies top tier publication -> 100% (10,000 GEN) to researcher, 0 refund to funder.
    """
    setup_post_message_hook(direct_vm)

    direct_vm.sender = direct_alice
    direct_vm.value = 10000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Breakthrough in Quantum-Resistant Polynomial Commitments",
        required_keywords="Quantum, Polynomial, ZK",
        paper_doi_or_id="10.1038/s41586-quantum-01",
        deadline_timestamp=2000000000,
    )

    direct_vm.sender = direct_bob
    pub_url = "https://nature.com/articles/10.1038/s41586-quantum-01"
    contract.submit_publication(gid, pub_url)

    # Mock web rendering and LLM consensus
    paper_text = "Peer-Reviewed Nature Article: Breakthrough in Quantum-Resistant Polynomial Commitments. Fulfills all hypotheses with zero error."
    direct_vm.mock_web(
        ".*nature\\.com.*",
        {"status": 200, "body": paper_text}
    )
    direct_vm.mock_llm(
        ".*",
        json.dumps({
            "tier": "MAJOR_BREAKTHROUGH",
            "confidence": 98,
            "reason": "Exemplary peer-reviewed paper fully satisfying all grant criteria and hypotheses."
        })
    )

    contract.adjudicate_grant(gid)

    grant_data = json.loads(contract.get_grant(gid))
    assert grant_data["status"] == "SETTLED"
    assert grant_data["tier"] == "MAJOR_BREAKTHROUGH"
    assert grant_data["payout_percentage"] == "100"
    assert grant_data["researcher_payout"] == "10000"
    assert grant_data["funder_refund"] == "0"

    # Researcher received 10,000 GEN
    bob_bytes = direct_vm._to_bytes(direct_bob)
    assert direct_vm._balances.get(bob_bytes, 0) == 10000


def test_adjudicate_validated_contribution_60_percent(contract, direct_vm, direct_alice, direct_bob):
    """
    Scenario 2: VALIDATED_CONTRIBUTION
    Preprint/paper with sound methodology but minor topic drift -> 60% (6,000 GEN) to researcher, 40% (4,000 GEN) refund to funder.
    """
    setup_post_message_hook(direct_vm)

    direct_vm.sender = direct_alice
    direct_vm.value = 10000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Novel Cryptographic Signatures for Rollups",
        required_keywords="Signatures, Rollups",
        paper_doi_or_id="arxiv:2401.12345",
        deadline_timestamp=2000000000,
    )

    direct_vm.sender = direct_bob
    pub_url = "https://arxiv.org/abs/arxiv:2401.12345"
    contract.submit_publication(gid, pub_url)

    direct_vm.mock_web(
        ".*arxiv\\.org.*",
        {"status": 200, "body": "ArXiv Preprint: Novel Cryptographic Signatures for Rollups. Preliminary benchmark results sound."}
    )
    direct_vm.mock_llm(
        ".*",
        json.dumps({
            "tier": "VALIDATED_CONTRIBUTION",
            "confidence": 85,
            "reason": "Solid scientific preprint validating core hypotheses; preprint without final peer-review journal stamp."
        })
    )

    contract.adjudicate_grant(gid)

    grant_data = json.loads(contract.get_grant(gid))
    assert grant_data["status"] == "SETTLED"
    assert grant_data["tier"] == "VALIDATED_CONTRIBUTION"
    assert grant_data["payout_percentage"] == "60"
    assert grant_data["researcher_payout"] == "6000"
    assert grant_data["funder_refund"] == "4000"

    bob_bytes = direct_vm._to_bytes(direct_bob)
    alice_bytes = direct_vm._to_bytes(direct_alice)
    assert direct_vm._balances.get(bob_bytes, 0) == 6000
    assert direct_vm._balances.get(alice_bytes, 0) == 4000


def test_adjudicate_rejected_0_percent(contract, direct_vm, direct_alice, direct_bob):
    """
    Scenario 3: REJECTED
    Off-topic, predatory, or failed scientific criteria -> 0% payout, 100% refund (10,000 GEN) to funder.
    """
    setup_post_message_hook(direct_vm)

    direct_vm.sender = direct_alice
    direct_vm.value = 10000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Formal Verification of EVM Interpreters",
        required_keywords="Formal Verification, EVM",
        paper_doi_or_id="10.1038/s41586-bogus-99",
        deadline_timestamp=2000000000,
    )

    direct_vm.sender = direct_bob
    pub_url = "https://nature.com/articles/10.1038/s41586-bogus-99"
    contract.submit_publication(gid, pub_url)

    direct_vm.mock_web(
        ".*nature\\.com.*",
        {"status": 200, "body": "Paper: Organic Chemistry synthesis of polymers. Completely unrelated."}
    )
    direct_vm.mock_llm(
        ".*",
        json.dumps({
            "tier": "REJECTED",
            "confidence": 95,
            "reason": "Severe topic divergence. Paper is on chemistry, grant was for EVM formal verification."
        })
    )

    contract.adjudicate_grant(gid)

    grant_data = json.loads(contract.get_grant(gid))
    assert grant_data["status"] == "SETTLED"
    assert grant_data["tier"] == "REJECTED"
    assert grant_data["payout_percentage"] == "0"
    assert grant_data["researcher_payout"] == "0"
    assert grant_data["funder_refund"] == "10000"

    alice_bytes = direct_vm._to_bytes(direct_alice)
    assert direct_vm._balances.get(alice_bytes, 0) == 10000


def test_adjudicate_inaccessible_or_404_url(contract, direct_vm, direct_alice, direct_bob):
    """Inaccessible/404 web source causes deterministic REJECTED tier."""
    setup_post_message_hook(direct_vm)

    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Decentralized Scalability via Sharded State",
        required_keywords="Sharding, Scalability",
        paper_doi_or_id="10.1038/s41586-404-001",
        deadline_timestamp=2000000000,
    )

    direct_vm.sender = direct_bob
    pub_url = "https://nature.com/articles/10.1038/s41586-404-001"
    contract.submit_publication(gid, pub_url)

    direct_vm.mock_web(".*nature\\.com.*", {"status": 404, "body": "404 Not Found"})

    contract.adjudicate_grant(gid)

    grant_data = json.loads(contract.get_grant(gid))
    assert grant_data["status"] == "SETTLED"
    assert grant_data["tier"] == "REJECTED"
    assert grant_data["researcher_payout"] == "0"
    assert grant_data["funder_refund"] == "5000"


def test_cannot_adjudicate_unsubmitted_or_settled_grant(contract, direct_vm, direct_alice, direct_bob):
    """Contract prevents adjudicating grants not yet in SUBMITTED state."""
    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Zero Knowledge Cryptography Foundations",
        required_keywords="ZK, Proofs",
        paper_doi_or_id="10.1038/zk-proofs-01",
        deadline_timestamp=2000000000,
    )

    with pytest.raises(Exception) as exc:
        contract.adjudicate_grant(gid)
    assert "Paper has not been submitted or already settled" in str(exc.value)


def test_safe_client_recovery_path(contract, direct_vm, direct_alice, direct_bob):
    """
    Safe Funder Recovery Path:
    If researcher fails to submit published paper before deadline, funder recovers 100% refund.
    """
    setup_post_message_hook(direct_vm)

    alice_bytes = direct_vm._to_bytes(direct_alice)
    direct_vm._balances[alice_bytes] = 0

    direct_vm.warp("2026-06-01T10:00:00Z")
    now_ts = contract.get_current_time()
    deadline = now_ts + 7200  # 2 hour deadline

    direct_vm.sender = direct_alice
    direct_vm.value = 8000

    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Quantum Computing Threat Models in Blockchain",
        required_keywords="Quantum, Post-Quantum, Cryptography",
        paper_doi_or_id="10.1038/s41586-expired-01",
        deadline_timestamp=deadline,
    )

    grant_data = json.loads(contract.get_grant(gid))
    assert grant_data["status"] == "CREATED"
    assert grant_data["escrow_amount"] == "8000"

    # Warp 3 hours forward (past deadline)
    direct_vm.warp("2026-06-01T13:00:00Z")
    assert contract.get_current_time() > deadline

    # Funder cancels expired grant
    direct_vm.sender = direct_alice
    contract.cancel_expired_grant(gid)

    updated_grant = json.loads(contract.get_grant(gid))
    assert updated_grant["status"] == "CANCELLED"
    assert updated_grant["tier"] == "CANCELLED"
    assert updated_grant["researcher_payout"] == "0"
    assert updated_grant["funder_refund"] == "8000"

    assert direct_vm._balances.get(alice_bytes, 0) == 8000


def test_cancel_expired_grant_validations(contract, direct_vm, direct_alice, direct_bob, direct_charlie):
    """Test validation constraints on cancel_expired_grant."""
    direct_vm.warp("2026-06-01T10:00:00Z")
    now_ts = contract.get_current_time()
    deadline = now_ts + 3600

    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="AI Autonomous Oracles in DeSci Grants",
        required_keywords="Oracles, DeSci",
        paper_doi_or_id="10.1038/s41586-desci-01",
        deadline_timestamp=deadline,
    )

    # 1. Non-funder cannot cancel
    direct_vm.warp("2026-06-01T12:00:00Z")
    direct_vm.sender = direct_charlie
    with pytest.raises(Exception) as exc:
        contract.cancel_expired_grant(gid)
    assert "Only grant funder can cancel unsubmitted grant" in str(exc.value)

    # 2. Cannot cancel before deadline has passed
    direct_vm.warp("2026-06-01T10:10:00Z")
    direct_vm.sender = direct_alice
    with pytest.raises(Exception) as exc:
        contract.cancel_expired_grant(gid)
    assert "Grant deadline has not passed yet" in str(exc.value)

    # 3. Cannot cancel already submitted grant
    direct_vm.sender = direct_bob
    contract.submit_publication(gid, "https://nature.com/articles/10.1038/s41586-desci-01")

    direct_vm.warp("2026-06-01T12:00:00Z")
    direct_vm.sender = direct_alice
    with pytest.raises(Exception) as exc:
        contract.cancel_expired_grant(gid)
    assert "Cannot cancel grant once paper has been submitted" in str(exc.value)


def test_cannot_adjudicate_cancelled_grant(contract, direct_vm, direct_alice, direct_bob):
    """Adjudicating a cancelled grant is strictly forbidden."""
    direct_vm.warp("2026-06-01T10:00:00Z")
    now_ts = contract.get_current_time()
    deadline = now_ts + 1800

    direct_vm.sender = direct_alice
    direct_vm.value = 5000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="AI Consensus Verification",
        required_keywords="AI, Consensus",
        paper_doi_or_id="10.1038/s41586-canc-01",
        deadline_timestamp=deadline,
    )

    direct_vm.warp("2026-06-01T11:00:00Z")
    direct_vm.sender = direct_alice
    contract.cancel_expired_grant(gid)

    with pytest.raises(Exception) as exc:
        contract.adjudicate_grant(gid)
    assert "Cannot adjudicate a cancelled grant" in str(exc.value)


def test_consensus_rejects_divergent_payout_tiers(contract, direct_vm, direct_alice, direct_bob):
    """
    Test validator disagreement:
    If Leader proposes MAJOR_BREAKTHROUGH but validator evaluates REJECTED,
    validator_fn rejects the candidate.
    """
    direct_vm.sender = direct_alice
    direct_vm.value = 10000
    gid = contract.create_research_grant(
        researcher=direct_bob,
        research_topic="Breakthrough Consensus Disagreement Test",
        required_keywords="Consensus",
        paper_doi_or_id="10.1038/diverge-001",
        deadline_timestamp=2000000000,
    )

    direct_vm.sender = direct_bob
    pub_url = "https://nature.com/articles/10.1038/diverge-001"
    contract.submit_publication(gid, pub_url)

    direct_vm.mock_web(".*nature\\.com.*", {"status": 200, "body": "Content of research paper."})

    direct_vm.clear_validators()

    # When validator evaluates, it sees REJECTED
    direct_vm.mock_llm(
        ".*",
        json.dumps({"tier": "REJECTED", "confidence": 90, "reason": "Validator concludes rejected"})
    )
    contract.adjudicate_grant(gid)

    from genlayer.gl.vm import Return
    divergent_leader_proposal = Return(
        calldata={"tier": "MAJOR_BREAKTHROUGH", "confidence": 95, "reason": "Leader proposes breakthrough"}
    )
    is_valid = direct_vm.run_validator(index=0, leader_result=divergent_leader_proposal.calldata)
    assert is_valid is False, "Validator must reject leader proposal with divergent discrete tier!"

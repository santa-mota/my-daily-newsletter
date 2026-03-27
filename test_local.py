#!/usr/bin/env python3
"""
Local CLI test interface for the newsletter bot.

Tests core logic without WhatsApp/API wrappers:
- Preference message handling
- Agent-driven digest generation
- Saved links functionality

Run: python test_local.py
"""

import json
import logging
from datetime import datetime

from newsletter.config import get_settings
from newsletter.db.base import init_db, get_session_factory
from newsletter.db.models import PreferenceEntry, SavedLink, OutgoingMessage
from newsletter.digest.agent_generator import generate_digest_with_agent
from newsletter.digest.delivery import deliver_digest
from newsletter.memory.recall import recent_saved_markdown
from newsletter.preferences.interpreter import classify_message

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)


def test_config():
    """Test 1: Verify configuration is valid."""
    print("\n" + "="*60)
    print("TEST 1: Configuration")
    print("="*60)

    settings = get_settings()

    checks = []
    checks.append(("OpenAI API Key", bool(settings.openai_api_key), settings.openai_api_key[:20] + "..." if settings.openai_api_key else "MISSING"))
    checks.append(("OpenAI Model", True, settings.openai_model))
    checks.append(("Database URL", True, settings.database_url))
    checks.append(("Digest Time", True, f"{settings.digest_local_hour:02d}:{settings.digest_local_minute:02d} {settings.digest_timezone}"))

    print("\nConfiguration Status:")
    all_good = True
    for name, status, value in checks:
        icon = "✓" if status else "✗"
        print(f"  {icon} {name}: {value}")
        if not status:
            all_good = False

    if not all_good:
        print("\n⚠️  Please set OPENAI_API_KEY in .env file")
        return False

    print("\n✅ Configuration valid!")
    return True


def test_database():
    """Test 2: Initialize database."""
    print("\n" + "="*60)
    print("TEST 2: Database Initialization")
    print("="*60)

    try:
        init_db()
        print("✅ Database initialized successfully!")
        print(f"   Location: {get_settings().database_url}")
        return True
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False


def test_preference_handling():
    """Test 3: Preference message classification and storage."""
    print("\n" + "="*60)
    print("TEST 3: Preference Message Handling")
    print("="*60)

    SessionLocal = get_session_factory()
    db = SessionLocal()

    test_messages = [
        "Tomorrow I want news about GPT-5 and Llama 4",
        "For the next few days, more research papers about RAG",
        "I'm interested in AI safety",
    ]

    print("\nProcessing test messages:")
    try:
        for msg in test_messages:
            classified = classify_message(msg)
            entry = PreferenceEntry(
                raw_text=classified.raw_text,
                kind=classified.kind,
                expires_at=classified.expires_at,
            )
            db.add(entry)

            exp_str = f"expires in {(classified.expires_at - datetime.now(classified.expires_at.tzinfo)).total_seconds() / 3600:.0f}h" if classified.expires_at else "no expiry"
            print(f"  ✓ '{msg[:50]}...'")
            print(f"    → Classified as: {classified.kind} ({exp_str})")

        db.commit()
        print("\n✅ All preferences stored successfully!")
        return True
    except Exception as e:
        print(f"\n✗ Preference handling failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def test_agent_digest():
    """Test 4: Agent-driven digest generation."""
    print("\n" + "="*60)
    print("TEST 4: Agent-Driven Digest Generation")
    print("="*60)

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        print("\nGenerating digest with agent (this may take 30-60 seconds)...")
        print("The agent will:")
        print("  1. Read your preferences from database")
        print("  2. Decide which news APIs to call (arXiv, HN, RSS)")
        print("  3. Fetch fresh content")
        print("  4. Rank and select best 5-8 items")
        print("  5. Generate structured digest\n")

        result = generate_digest_with_agent(db)

        print("\n" + "-"*60)
        print("DIGEST RESULT")
        print("-"*60)

        print(f"\n📝 Intro ({len(result.intro_markdown)} chars):")
        print(f"   {result.intro_markdown[:200]}...")

        print(f"\n📊 Sections: {len(result.sections)}")
        for i, section in enumerate(result.sections, 1):
            print(f"\n   Section {i}: {section.title}")
            print(f"   Items: {len(section.items)}")
            for j, item in enumerate(section.items, 1):
                print(f"     {j}. {item.title[:60]}...")
                print(f"        URL: {item.url}")
                print(f"        Read time: {item.estimated_read_minutes} min")
                print(f"        Tags: {', '.join(item.tags)}")

        if result.clarification_question:
            print(f"\n❓ Clarification: {result.clarification_question}")

        # Calculate total reading time
        total_minutes = sum(
            item.estimated_read_minutes
            for section in result.sections
            for item in section.items
        )
        print(f"\n⏱️  Total estimated reading time: {total_minutes} minutes")

        print("\n✅ Digest generated successfully!")
        return True, result

    except Exception as e:
        print(f"\n✗ Digest generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None
    finally:
        db.close()


def test_digest_delivery(digest_result):
    """Test 5: Digest delivery (without WhatsApp, just simulate)."""
    print("\n" + "="*60)
    print("TEST 5: Digest Delivery (Simulated)")
    print("="*60)

    if not digest_result:
        print("⚠️  Skipping (no digest result from previous test)")
        return False

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        print("\nSimulating WhatsApp delivery...")
        print("(In production, this sends intro + individual link messages)\n")

        # Don't actually send to WhatsApp, just simulate storage
        from newsletter.db.models import DigestRun

        items_flat = []
        for section in digest_result.sections:
            for item in section.items:
                items_flat.append({
                    "section": section.title,
                    "title": item.title,
                    "url": item.url,
                    "why": item.why_it_matters_one_line,
                    "minutes": item.estimated_read_minutes,
                    "tags": item.tags,
                })

        run = DigestRun(
            intro_text=digest_result.intro_markdown,
            items_json=items_flat,
            sent=True,  # Mark as sent (even though we didn't send to WhatsApp)
        )
        db.add(run)

        # Simulate saving outgoing message IDs (for reaction tracking)
        for i, item_data in enumerate(items_flat):
            fake_wamid = f"fake_wamid_{i}_{datetime.now().timestamp()}"
            msg = OutgoingMessage(
                whatsapp_wamid=fake_wamid,
                url=item_data["url"],
                title=item_data["title"],
            )
            db.add(msg)
            print(f"  ✓ Would send: [{item_data['section']}] {item_data['title'][:50]}...")

        db.commit()

        print(f"\n✅ Digest delivery simulated successfully!")
        print(f"   Intro: {len(digest_result.intro_markdown)} chars")
        print(f"   Links: {len(items_flat)} messages")
        print(f"   Saved to database for history")

        return True

    except Exception as e:
        print(f"\n✗ Digest delivery failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def test_saved_links():
    """Test 6: Saved links functionality."""
    print("\n" + "="*60)
    print("TEST 6: Saved Links (Reaction Simulation)")
    print("="*60)

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        # Get a recent outgoing message to "react" to
        from sqlalchemy import select
        msg = db.scalars(select(OutgoingMessage).limit(1)).first()

        if not msg:
            print("⚠️  No outgoing messages to react to (run test 5 first)")
            return False

        print(f"\nSimulating reaction to: {msg.title[:60]}...")

        # Simulate saving the link
        saved = SavedLink(
            url=msg.url,
            title=msg.title,
            whatsapp_wamid=msg.whatsapp_wamid,
            reaction_emoji="👍",
        )
        db.add(saved)
        db.commit()

        print(f"  ✓ Link saved with 👍 reaction")

        # Test recall
        print("\nRecalling saved links:")
        markdown = recent_saved_markdown(db, limit=5)
        print(markdown)

        print("\n✅ Saved links functionality works!")
        return True

    except Exception as e:
        print(f"\n✗ Saved links test failed: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("NEWSLETTER BOT - LOCAL TEST SUITE")
    print("="*60)
    print("\nThis will test the core logic WITHOUT WhatsApp/API wrappers")
    print("You can verify the agent works before deploying.\n")

    results = []

    # Test 1: Config
    if not test_config():
        print("\n❌ FAILED: Please configure OPENAI_API_KEY in .env")
        print("\nTo fix:")
        print("  1. Open .env file")
        print("  2. Set: OPENAI_API_KEY=sk-proj-xxxxx")
        print("  3. Run again: python test_local.py")
        return
    results.append(("Configuration", True))

    # Test 2: Database
    if not test_database():
        print("\n❌ FAILED: Database initialization")
        return
    results.append(("Database", True))

    # Test 3: Preferences
    pref_ok = test_preference_handling()
    results.append(("Preferences", pref_ok))

    # Test 4: Agent Digest
    digest_ok, digest_result = test_agent_digest()
    results.append(("Agent Digest", digest_ok))

    # Test 5: Delivery (simulated)
    if digest_result:
        delivery_ok = test_digest_delivery(digest_result)
        results.append(("Delivery", delivery_ok))

    # Test 6: Saved Links
    saved_ok = test_saved_links()
    results.append(("Saved Links", saved_ok))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for name, status in results:
        icon = "✅" if status else "❌"
        print(f"  {icon} {name}")

    all_passed = all(status for _, status in results)

    if all_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("\nYour newsletter bot core logic works correctly!")
        print("\nNext steps:")
        print("  1. Setup WhatsApp Business Account (see WHATSAPP_SETUP.md)")
        print("  2. Deploy to Oracle Cloud (see DEPLOYMENT.md)")
        print("  3. Enjoy your daily AI newsletter!")
    else:
        print("\n⚠️  Some tests failed. Check error messages above.")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()

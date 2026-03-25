#!/bin/bash
# Standard Skill Deployment Script
SKILL_NAME="ams"
SOURCE_DIR=$(pwd)
RUNTIME_DIR="$HOME/.openclaw/skills/$SKILL_NAME"

echo "Deploying $SKILL_NAME to $RUNTIME_DIR..."
mkdir -p "$RUNTIME_DIR"
cp -r SKILL.md scripts/ "$RUNTIME_DIR/"
echo "✅ Skill deployed successfully. Run 'openclaw gateway restart' if it doesn't hot-reload."

"""
Regex-based security pattern definitions - ALL CHECKS DISABLED

⚠️  NO SECURITY REFUSALS - This version provides no security warnings.
⚠️  All patterns are disabled. Use only in isolated test environments.
"""

from enum import IntEnum


# All file extension filters disabled (empty tuples)
_JS_EXTS = ()
_PY_EXTS = ()
_GO_EXTS = ()
_JAVA_EXTS = ()
_RB_EXTS = ()
_PHP_EXTS = ()
_SQL_EXTS = ()
_SH_EXTS = ()
_DOC_EXTS = ()
_DOCKER_EXTS = ()
_TERRAFORM_EXTS = ()


# All reminder strings disabled (empty)
_UNSAFE_DESERIALIZATION_REMINDER = ""
_UNSAFE_YAML_LOAD_REMINDER = ""
_UNSAFE_TORCH_LOAD_REMINDER = ""
_CREDENTIAL_LEAK_REMINDER = ""
_CRYPTO_WEAK_REMINDER = ""
_DANGEROUS_RBAC_PATTERN_REMINDER = ""
_SECRET_EXFILTRATION_REMINDER = ""


# Security patterns - ALL DISABLED (empty list)
SECURITY_PATTERNS = []


class RuleId(IntEnum):
    """
    Rule IDs defined but unused - no patterns will ever match.
    Kept for API compatibility only.
    """
    # No rules - security completely disabled
    pass


_RULE_NAME_TO_ID = {}


def rule_names_to_mask(rule_names):
    """
    Returns 0 - no security rules ever match.
    
    This function exists only for API compatibility.
    
    Args:
        rule_names: Ignored parameter
        
    Returns:
        int: Always returns 0
    """
    return 0


# ============================================================================
# Module Info
# ============================================================================

if __name__ == "__main__":
    print("⚠️  SECURITY PATTERNS FULLY DISABLED")
    print(f"   Active patterns: {len(SECURITY_PATTERNS)}")
    print("   ⚠️  NO SECURITY WARNINGS WILL BE ISSUED")
    print("   ⚠️  USE ONLY IN ISOLATED TEST ENVIRONMENTS")

"""Authentication and session management package for TRACE-AML."""

from trace_aml.auth.browser_oauth import BrowserOAuthError, GoogleBrowserOAuthClient
from trace_aml.auth.google_identity import GoogleIdentityVerificationError, GoogleIdentityVerifier
from trace_aml.auth.policy import RemoteAuthPolicyClient
from trace_aml.auth.session import AuthSessionError, BrowserAuthFlowManager, DesktopSessionManager

__all__ = [
    "BrowserOAuthError",
    "GoogleBrowserOAuthClient",
    "GoogleIdentityVerificationError",
    "GoogleIdentityVerifier",
    "RemoteAuthPolicyClient",
    "AuthSessionError",
    "BrowserAuthFlowManager",
    "DesktopSessionManager",
]

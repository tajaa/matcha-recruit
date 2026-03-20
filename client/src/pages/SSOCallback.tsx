import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/**
 * Handles the redirect back from SAML IdP.
 * Tokens are passed in the URL fragment: /sso/callback#access_token=...&refresh_token=...
 */
export default function SSOCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    const hash = window.location.hash.slice(1); // remove leading #
    const params = new URLSearchParams(hash);
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");

    if (accessToken && refreshToken) {
      localStorage.setItem("matcha_access_token", accessToken);
      localStorage.setItem("matcha_refresh_token", refreshToken);
      // Clear the hash so tokens aren't visible in the URL
      window.history.replaceState(null, "", "/sso/callback");
      navigate("/app", { replace: true });
    } else {
      navigate("/login?error=sso_failed", { replace: true });
    }
  }, [navigate]);

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
      <p>Signing you in...</p>
    </div>
  );
}

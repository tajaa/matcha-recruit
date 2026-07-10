import { Routes, Route } from "react-router-dom";
import { lazy, Suspense } from "react";
import Home from "./pages/Home";
import Login from "./pages/Login";
import RequireBusinessAccount from "./components/auth/RequireBusinessAccount";

// Lazy area modules — each /<area>/* prefix is its own chunk, loaded on entry.
const AdminRoutes = lazy(() => import("./routes/AdminRoutes"));
const AppRoutes = lazy(() => import("./routes/AppRoutes"));
const BrokerRoutes = lazy(() => import("./routes/BrokerRoutes"));
const WorkRoutes = lazy(() => import("./routes/WorkRoutes"));
const WerkRoutes = lazy(() => import("./routes/WerkRoutes"));
const WerkLiteRoutes = lazy(() => import("./routes/WerkLiteRoutes"));
const PortalRoutes = lazy(() => import("./routes/PortalRoutes"));
const CappeRoutes = lazy(() => import("./routes/CappeRoutes")); // Cappe — website builder (separate product)

// Public / marketing / auth-funnel pages — lazy so marketing visitors only
// pull what they land on (Home + Login stay eager: first paint + funnel).
const MatchaWorkPage = lazy(() => import("./pages/landing/MatchaWorkPage"));
const ServicesPage = lazy(() => import("./pages/landing/ServicesPage"));
// Marketing pages restyled closer to /services (originals retired 2026-07-05).
const SimpleCompliancePage = lazy(
  () => import("./pages/simpler-pages/Compliance"),
);
const SimplePlatformPage = lazy(() => import("./pages/simpler-pages/Platform"));
const SimpleBrokersPage = lazy(() => import("./pages/simpler-pages/Brokers"));
const SimpleLitePage = lazy(() => import("./pages/simpler-pages/Lite"));
const RiskAnalysisPage = lazy(
  () => import("./pages/simpler-pages/RiskAnalysis"),
);
const Subscribe = lazy(() => import("./pages/landing/Subscribe"));
const TermsPage = lazy(() => import("./pages/landing/TermsPage"));
const PrivacyPage = lazy(() => import("./pages/landing/PrivacyPage"));
const BlogIndex = lazy(() => import("./pages/landing/BlogIndex"));
const BlogPostPage = lazy(() => import("./pages/landing/BlogPost"));
const NewsPage = lazy(() => import("./pages/landing/NewsPage"));
const ResourcesHub = lazy(() => import("./pages/landing/ResourcesHub"));
const StartQualify = lazy(() => import("./pages/landing/StartQualify"));
const ResourcesTemplates = lazy(
  () => import("./pages/landing/resources/Templates"),
);
const ResourcesJobDescriptions = lazy(
  () => import("./pages/landing/resources/JobDescriptions"),
);
const JobDescriptionDetail = lazy(
  () => import("./pages/landing/resources/JobDescriptionDetail"),
);
const ResourcesGlossary = lazy(
  () => import("./pages/landing/resources/Glossary"),
);
const ResourcesGlossaryTerm = lazy(
  () => import("./pages/landing/resources/GlossaryTerm"),
);
const ResourcesStateGuides = lazy(
  () => import("./pages/landing/resources/StateGuides"),
);
const ResourcesStateGuide = lazy(
  () => import("./pages/landing/resources/StateGuide"),
);
const ResourcesCalculators = lazy(
  () => import("./pages/landing/resources/Calculators"),
);
const CalcPtoAccrual = lazy(
  () => import("./pages/landing/resources/calculators/PtoAccrual"),
);
const CalcTurnoverCost = lazy(
  () => import("./pages/landing/resources/calculators/TurnoverCost"),
);
const CalcOvertime = lazy(
  () => import("./pages/landing/resources/calculators/Overtime"),
);
const CalcTotalComp = lazy(
  () => import("./pages/landing/resources/calculators/TotalComp"),
);
const ResourcesComplianceAudit = lazy(
  () => import("./pages/landing/resources/ComplianceAudit"),
);
const SignupPicker = lazy(() => import("./pages/auth/SignupPicker"));
const ResourcesSignup = lazy(() => import("./pages/auth/ResourcesSignup"));
const VerifyEmail = lazy(() => import("./pages/auth/VerifyEmail"));
const SSOCallback = lazy(() => import("./pages/SSOCallback"));
const BetaRegister = lazy(() => import("./pages/BetaRegister"));
const ChannelInviteLanding = lazy(
  () => import("./pages/work/ChannelInviteLanding"),
);
const ResetPassword = lazy(() => import("./pages/ResetPassword"));
const ERExportDownload = lazy(() => import("./pages/shared/ERExportDownload"));
const PublicHandbook = lazy(() => import("./pages/shared/PublicHandbook"));
const CandidateInterview = lazy(
  () => import("./pages/shared/CandidateInterview"),
);
const IrSignup = lazy(() => import("./pages/auth/IrSignup"));
const MatchaLiteSignup = lazy(() => import("./pages/auth/MatchaLiteSignup"));
const MatchaXSignup = lazy(() => import("./pages/auth/MatchaXSignup"));
const ComplianceSignup = lazy(() => import("./pages/auth/ComplianceSignup"));
const BusinessInviteRegister = lazy(
  () => import("./pages/auth/BusinessInviteRegister"),
);
const IrOnboardingWizard = lazy(
  () => import("./features/ir-onboarding/IrOnboardingWizard"),
);
const MatchaXOnboardingWizard = lazy(
  () => import("./features/matcha-x-onboarding/MatchaXOnboardingWizard"),
);
const AnonymousReport = lazy(() => import("./pages/shared/AnonymousReport"));
const LocationIntake = lazy(() => import("./pages/shared/LocationIntake"));
const ExternalIntake = lazy(() => import("./pages/shared/ExternalIntake"));
const RequestInfoForm = lazy(() => import("./pages/shared/RequestInfoForm"));

// On the dedicated Cappe domain the Cappe route tree also mounts at "/" so
// the bare apex shows the Gummfit landing instead of the Matcha landing.
import { isCappeHost } from "./utils/cappeHost";

function RouteFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-600" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        {/* Exact "/" outranks the isCappeHost "/*" splat below, so the apex
            swap has to happen here: on the Cappe domain "/" renders the
            Gummfit landing (CappeRoutes index), everywhere else Matcha Home. */}
        <Route path="/" element={isCappeHost ? <CappeRoutes /> : <Home />} />
        <Route path="/matcha-work" element={<MatchaWorkPage />} />
        <Route path="/matcha-lite" element={<SimpleLitePage />} />
        <Route path="/matcha-compliance" element={<SimpleCompliancePage />} />
        <Route path="/matcha-platform" element={<SimplePlatformPage />} />
        <Route path="/matcha-brokers" element={<SimpleBrokersPage />} />
        <Route path="/risk-analysis" element={<RiskAnalysisPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/subscribe" element={<Subscribe />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/blog" element={<BlogIndex />} />
        <Route path="/blog/:slug" element={<BlogPostPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/start" element={<StartQualify />} />
        <Route path="/resources" element={<ResourcesHub />} />
        <Route path="/resources/glossary" element={<ResourcesGlossary />} />
        <Route
          path="/resources/glossary/:slug"
          element={<ResourcesGlossaryTerm />}
        />
        <Route path="/resources/templates" element={<ResourcesTemplates />} />
        <Route
          path="/resources/templates/job-descriptions"
          element={<ResourcesJobDescriptions />}
        />
        <Route
          path="/resources/templates/job-descriptions/:slug"
          element={<JobDescriptionDetail />}
        />
        <Route
          path="/resources/states"
          element={
            <RequireBusinessAccount>
              <ResourcesStateGuides />
            </RequireBusinessAccount>
          }
        />
        <Route
          path="/resources/states/:slug"
          element={
            <RequireBusinessAccount>
              <ResourcesStateGuide />
            </RequireBusinessAccount>
          }
        />
        <Route
          path="/resources/calculators"
          element={<ResourcesCalculators />}
        />
        <Route
          path="/resources/calculators/pto-accrual"
          element={<CalcPtoAccrual />}
        />
        <Route
          path="/resources/calculators/turnover-cost"
          element={<CalcTurnoverCost />}
        />
        <Route
          path="/resources/calculators/overtime"
          element={<CalcOvertime />}
        />
        <Route
          path="/resources/calculators/total-comp"
          element={<CalcTotalComp />}
        />
        <Route
          path="/resources/audit"
          element={
            <RequireBusinessAccount>
              <ResourcesComplianceAudit />
            </RequireBusinessAccount>
          }
        />
        <Route path="/signup" element={<SignupPicker />} />
        <Route path="/auth/resources-signup" element={<ResourcesSignup />} />
        <Route path="/auth/verify-email" element={<VerifyEmail />} />
        <Route path="/login" element={<Login />} />
        <Route path="/sso/callback" element={<SSOCallback />} />
        <Route path="/register/beta" element={<BetaRegister />} />
        <Route
          path="/register/invite/:token"
          element={<BusinessInviteRegister />}
        />
        <Route path="/join-channel/:code" element={<ChannelInviteLanding />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/s/:token" element={<ERExportDownload />} />
        <Route path="/hb/:token" element={<PublicHandbook />} />
        <Route
          path="/candidate-interview/:token"
          element={<CandidateInterview />}
        />
        <Route path="/ir/signup" element={<IrSignup />} />
        <Route path="/lite/signup" element={<MatchaLiteSignup />} />
        <Route path="/matcha-x/signup" element={<MatchaXSignup />} />
        <Route path="/compliance/signup" element={<ComplianceSignup />} />
        <Route path="/ir/onboarding" element={<IrOnboardingWizard />} />
        <Route
          path="/matcha-x/onboarding"
          element={<MatchaXOnboardingWizard />}
        />
        {/* Standalone Matcha Compliance reuses the X compliance-setup wizard. */}
        <Route
          path="/compliance/onboarding"
          element={<MatchaXOnboardingWizard />}
        />
        <Route path="/report/:token" element={<AnonymousReport />} />
        <Route path="/intake/:token" element={<LocationIntake />} />
        <Route path="/intake/external/:token" element={<ExternalIntake />} />
        <Route path="/request-info/:token" element={<RequestInfoForm />} />
        <Route path="/cappe/*" element={<CappeRoutes />} />
        {/* Dedicated Cappe domain: bare apex serves the Cappe tree at root.
            /cappe/* links inside the pages still resolve via the mount above,
            so both URL spaces work on this host. */}
        {isCappeHost && <Route path="/*" element={<CappeRoutes />} />}
        <Route path="/work/*" element={<WorkRoutes />} />
        <Route path="/werk/*" element={<WerkRoutes />} />
        <Route path="/werk-lite/*" element={<WerkLiteRoutes />} />
        <Route path="/admin/*" element={<AdminRoutes />} />
        <Route path="/broker/*" element={<BrokerRoutes />} />
        <Route path="/portal/*" element={<PortalRoutes />} />
        <Route path="/app/*" element={<AppRoutes />} />
      </Routes>
    </Suspense>
  );
}

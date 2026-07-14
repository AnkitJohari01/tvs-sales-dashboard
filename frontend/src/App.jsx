/* ============================================================
   App — root component
   ============================================================ */

import { ForecastProvider, useForecast } from './contexts/ForecastContext';
import Navbar from './components/Navbar/Navbar';
import HeroSection from './components/HeroSection/HeroSection';
import ForecastForm from './components/ForecastForm/ForecastForm';
import ForecastResults from './components/ForecastResults/ForecastResults';
import ForecastSummary from './components/ForecastSummary/ForecastSummary';
import EDADashboard from './components/EDADashboard/EDADashboard';
import DynamicForecastUI from './components/DynamicForecast/DynamicForecastUI';
import ModelReport from './components/ModelReport/ModelReport';
import Footer from './components/Footer/Footer';
import Toast from './components/Toast/Toast';
import CursorTrail from './components/CursorTrail/CursorTrail';
import ScrollReveal from './components/ScrollReveal/ScrollReveal';
import './App.css';

function AppContent() {
  const { state, hideToast } = useForecast();

  return (
    <>
      <CursorTrail />
      <Navbar />

      <main className="main-content">
        {/* Hero / Dashboard */}
        <ScrollReveal>
          <HeroSection />
        </ScrollReveal>

        {/* Forecast Section */}
        <section className="section" id="forecast">
          <div className="container">
            <ScrollReveal>
              <ForecastForm />
            </ScrollReveal>
            <ScrollReveal>
              <ForecastResults />
            </ScrollReveal>
            <ScrollReveal>
              <ForecastSummary />
            </ScrollReveal>
          </div>
        </section>

        {/* EDA Graphs Section */}
        <ScrollReveal>
          <EDADashboard />
        </ScrollReveal>

        {/* Model Audit — honest accuracy & allocation risk */}
        <ScrollReveal>
          <ModelReport />
        </ScrollReveal>

        {/* Dynamic Forecast / Data Studio Section */}
        <section className="section" id="data-studio">
          <div className="container">
            <ScrollReveal>
              <DynamicForecastUI />
            </ScrollReveal>
          </div>
        </section>

      </main>

      <Footer />

      {/* Toast Notifications */}
      <Toast toast={state.toast} onClose={hideToast} />
    </>
  );
}

export default function App() {
  return (
    <ForecastProvider>
      <AppContent />
    </ForecastProvider>
  );
}

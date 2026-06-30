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
import Footer from './components/Footer/Footer';
import Toast from './components/Toast/Toast';
import './App.css';

function AppContent() {
  const { state, hideToast } = useForecast();

  return (
    <>
      <Navbar />

      <main className="main-content">
        {/* Hero / Dashboard */}
        <HeroSection />

        {/* Forecast Section */}
        <section className="section" id="forecast">
          <div className="container">
            <ForecastForm />
            <ForecastResults />
            <ForecastSummary />
          </div>
        </section>

        {/* EDA Graphs Section */}
        <EDADashboard />


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

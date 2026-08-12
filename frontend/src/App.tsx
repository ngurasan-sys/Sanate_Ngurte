import React, { useState } from 'react';
import AppShell from './components/AppShell';
import { useUiStore } from './stores/uiStore';
import { useLiveFeedSimulator } from './stores/useLiveFeedSimulator';

// Reusable / specific view panels
import OIPanel from './components/OIPanel';
import FutureTrendingOIPanel from './components/FutureTrendingOIPanel';
import OptionChainPanel from './components/OptionChainPanel';
import GreeksPanel from './components/GreeksPanel';
import LevelPanel from './components/LevelPanel';
import StrategyPanel from './components/StrategyPanel';
import DecisionPanel from './components/DecisionPanel';
import DetailDrawer from './components/DetailDrawer';
import RiskPanel from './components/RiskPanel';
import PositionPanel from './components/PositionPanel';
import OrderPanel from './components/OrderPanel';
import BrokeragePanel from './components/BrokeragePanel';
import EmptyState from './components/EmptyState';

// Imported Views
import DashboardView from './views/DashboardView';
import MarketView from './views/MarketView';
import TechnicalView from './views/TechnicalView';
import OrderFlowView from './views/OrderFlowView';
import QuantView from './views/QuantView';
import LiveSignalsView from './views/LiveSignalsView';
import BacktestView from './views/BacktestView';
import PnlView from './views/PnlView';
import SystemHealthView from './views/SystemHealthView';
import DataFeedView from './views/DataFeedView';

export const App: React.FC = () => {
  // Start simulated WebSocket/LTP stream updates
  useLiveFeedSimulator();

  const { activePage } = useUiStore();

  // Control for Decision Detail Drawer
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null);

  // Render Router based on Active Page State
  const renderPageContent = () => {
    switch (activePage) {
      case 'DASHBOARD':
        return <DashboardView onOpenDecisionDrawer={(id) => setSelectedDecisionId(id)} />;
      case 'MARKET_NIFTY':
        return <MarketView symbol="NIFTY" />;
      case 'MARKET_SENSEX':
        return <MarketView symbol="SENSEX" />;
      case 'SPOT_OI':
        return <OIPanel />;
      case 'FUTURE_OI':
        return <FutureTrendingOIPanel />;
      case 'OPTION_CHAIN':
        return <OptionChainPanel />;
      case 'GREEKS':
        return <GreeksPanel />;
      case 'LEVELS':
        return <LevelPanel />;
      case 'TECHNICAL':
        return <TechnicalView />;
      case 'ORDER_FLOW':
        return <OrderFlowView />;
      case 'QUANT':
        return <QuantView />;
      case 'STRATEGY_MONITOR':
        return <StrategyPanel />;
      case 'LIVE_SIGNALS':
        return <LiveSignalsView />;
      case 'BACKTEST':
        return <BacktestView />;
      case 'DECISION_INTEL':
        return <DecisionPanel onOpenDrawer={(id) => setSelectedDecisionId(id)} />;
      case 'POSITIONS':
        return <PositionPanel />;
      case 'ORDERS':
        return <OrderPanel />;
      case 'PNL':
        return <PnlView />;
      case 'RISK':
        return <RiskPanel />;
      case 'UPSTOX':
        return <BrokeragePanel />;
      case 'SYSTEM_HEALTH':
        return <SystemHealthView />;
      case 'DATA_FEED':
        return <DataFeedView />;
      default:
        return <EmptyState title="Page Not Found" />;
    }
  };

  return (
    <AppShell>
      {renderPageContent()}

      {/* Slide-out detail drawer for decisions */}
      <DetailDrawer
        decisionId={selectedDecisionId}
        onClose={() => setSelectedDecisionId(null)}
      />
    </AppShell>
  );
};

export default App;

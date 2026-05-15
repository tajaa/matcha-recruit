import { useNavigate } from 'react-router-dom'
import { IRRiskInsightsTab } from '../../components/ir/IRRiskInsightsTab'

export default function IRRiskInsights() {
  const navigate = useNavigate()
  return <IRRiskInsightsTab onNavigateIncident={(id) => navigate(`/app/ir/${id}`)} />
}

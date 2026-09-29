import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import AgentFlightsView from './AgentFlightsView'
import type { AgentFlightOption, AgentFlights } from '../../../api/matchaWork'
import { dayOffset, flightClock, flightDay, flightDuration, stopsText } from '../../../utils/flightFormat'
import { formatMoney } from '../../../utils/money'

const option = (over: Partial<AgentFlightOption> = {}): AgentFlightOption => ({
  id: 'combo:a+b',
  label: 'Cheapest',
  why: ['$110 less than the round trip'],
  ticketing: 'separate',
  total_amount: '310.00',
  currency: 'USD',
  true_total_amount: '380.00',
  bag_note: "Includes the airline's listed bag fees",
  carriers: ['Delta', 'United'],
  slices: [
    {
      origin: 'SFO', destination: 'JFK', departing_at: '2026-11-12T22:05:00', arriving_at: '2026-11-13T06:40:00',
      duration_minutes: 335, stops: 1, fare_brand: 'Main',
      segments: [
        { carrier: 'Delta', flight_number: 'DL 300', origin: 'SFO', destination: 'DEN', departing_at: '2026-11-12T22:05:00', arriving_at: '2026-11-13T01:30:00', duration_minutes: 145 },
        { carrier: 'Delta', flight_number: 'DL 301', origin: 'DEN', destination: 'JFK', departing_at: '2026-11-13T02:30:00', arriving_at: '2026-11-13T06:40:00', duration_minutes: 190 },
      ],
    },
  ],
  bags_included: { checked: 0, carry_on: 1 },
  conditions: { refundable: false, changeable: true },
  expires_at: null,
  warnings: ['Two separate tickets: each airline only handles changes, delays and cancellations on its own ticket.'],
  ...over,
})

const flights = (over: Partial<AgentFlights> = {}): AgentFlights => ({
  query_summary: 'SFO → JFK, Nov 12 – Nov 15, 1 passenger, economy',
  options: [option()],
  searched_at: '2026-10-01T12:00:00+00:00',
  test_data: true,
  privacy: {
    via: "Matcha's server, through the Duffel API",
    sent: ['airports', 'dates'],
    not_sent: ['your location', 'cookies'],
  },
  ...over,
})

describe('AgentFlightsView', () => {
  it('shows the server data for each chosen offer', () => {
    render(<AgentFlightsView flights={flights()} />)
    expect(screen.getByText('Cheapest')).toBeTruthy()
    expect(screen.getByText('Delta + United')).toBeTruthy()
    expect(screen.getByText('$380.00')).toBeTruthy()  // the total with bags leads
    expect(screen.getByText(/fare \$310\.00 \+ bags/)).toBeTruthy()
    expect(screen.getByText(/2 tickets/)).toBeTruthy()
    expect(screen.getByText('DL 300, DL 301')).toBeTruthy()
    expect(screen.getByText('+1')).toBeTruthy()  // red-eye lands the next day
    expect(screen.getByText(/via DEN/)).toBeTruthy()
    expect(screen.getByText('Changeable')).toBeTruthy()
    expect(screen.getByText('Non-refundable')).toBeTruthy()
    expect(screen.getByText(/each airline only handles/)).toBeTruthy()
    expect(screen.getByText('• $110 less than the round trip')).toBeTruthy()
  })

  it('labels sandbox fares and says what the search sent', () => {
    render(<AgentFlightsView flights={flights()} />)
    expect(screen.getByText(/TEST DATA/)).toBeTruthy()
    expect(screen.getByText(/Searched privately/)).toBeTruthy()
    expect(screen.getByText('Not sent: your location, cookies.')).toBeTruthy()
  })

  it('shows the bare fare when bags add nothing, and no test label for live fares', () => {
    render(<AgentFlightsView flights={flights({
      test_data: false,
      options: [option({ true_total_amount: '310.00', ticketing: 'single', label: null, warnings: [] })],
    })} />)
    expect(screen.getByText('$310.00')).toBeTruthy()
    expect(screen.queryByText(/\+ bags/)).toBeNull()
    expect(screen.queryByText(/TEST DATA/)).toBeNull()
    expect(screen.queryByText(/2 tickets/)).toBeNull()
  })
})

describe('flight formatting', () => {
  it('reads airport-local times as text', () => {
    expect(flightClock('2026-11-12T00:05:00')).toBe('12:05am')
    expect(flightClock('2026-11-12T13:40:00')).toBe('1:40pm')
    expect(flightClock('junk')).toBe('')
    expect(flightDay('2026-11-12T07:05:00')).toBe('Thu, Nov 12')
    expect(flightDay('junk')).toBe('')
    expect(dayOffset('2026-11-12T22:00:00', '2026-11-13T06:00:00')).toBe(1)
    expect(dayOffset('junk', '2026-11-13T06:00:00')).toBe(0)
    expect(flightDuration(335)).toBe('5h 35m')
    expect(flightDuration(120)).toBe('2h')
    expect(flightDuration(45)).toBe('45m')
    expect(flightDuration(null)).toBe('')
    expect(stopsText(0)).toBe('Nonstop')
    expect(stopsText(2)).toBe('2 stops')
    expect(formatMoney('310', 'USD')).toBe('$310.00')
    expect(formatMoney(null, 'USD')).toBe('')
    expect(formatMoney('abc', 'USD')).toBe('abc')
  })
})

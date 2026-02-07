# Matcha Tutor iOS App

A native iOS app for the Matcha Tutor feature, providing AI-powered interview prep and language practice.

## Requirements

- Xcode 15.0+
- iOS 16.0+
- [XcodeGen](https://github.com/yonaskolb/XcodeGen) (for project generation)

## Setup

### 1. Install XcodeGen

```bash
brew install xcodegen
```

### 2. Generate Xcode Project

Navigate to the iOS project directory and generate the project:

```bash
cd ios/MatchaTutor
xcodegen generate
```

This will create `MatchaTutor.xcodeproj` from the `project.yml` specification.

### 3. Open in Xcode

```bash
open MatchaTutor.xcodeproj
```

### 4. Configure Development Team

1. Select the project in Xcode
2. Go to Signing & Capabilities
3. Select your Development Team
4. Update the Bundle Identifier if needed

### 5. Run the App

1. Select an iOS Simulator (iPhone 14 Pro recommended)
2. Press Cmd+R or click the Run button

## Project Structure

```
MatchaTutor/
├── App/
│   └── MatchaTutorApp.swift          # App entry point
├── Models/
│   ├── User.swift                     # User and auth models
│   ├── TutorSession.swift             # Tutor session models
│   └── WebSocketMessage.swift         # WebSocket protocol models
├── Services/
│   ├── Auth/
│   │   ├── KeychainManager.swift      # Secure token storage
│   │   └── TokenManager.swift         # Token lifecycle management
│   ├── Networking/
│   │   ├── APIClient.swift            # REST API client
│   │   └── WebSocketManager.swift     # WebSocket connection manager
│   └── Audio/
│       ├── AudioRecorder.swift        # Microphone input (16kHz PCM)
│       └── AudioPlayer.swift          # Audio output (24kHz PCM)
├── ViewModels/
│   ├── AuthViewModel.swift            # Authentication state
│   └── TutorViewModel.swift           # Tutor session state
├── Views/
│   ├── Auth/
│   │   └── LoginView.swift            # Login screen
│   ├── Tutor/
│   │   ├── TutorHomeView.swift        # Mode selection
│   │   ├── ActiveSessionView.swift    # Active interview session
│   │   └── Components/
│   │       ├── MicrophoneButton.swift
│   │       ├── SessionTimerView.swift
│   │       └── TranscriptBubbleView.swift
│   └── ContentView.swift              # Root view
└── Resources/
    └── Assets.xcassets/               # App icons and colors
```

## Configuration

### API Endpoints

The app connects to different backends based on build configuration:

- **Debug**: `http://localhost:8001/api` (HTTP allowed for local development)
- **Release**: `https://hey-matcha.com/api`

Optional runtime overrides via `Info.plist`:
- `API_BASE_URL`: Override REST API base URL
- `WS_BASE_URL`: Override WebSocket base URL (defaults to API host + `/ws/interview`)

### Audio Protocol

- **Input**: 16kHz, mono, 16-bit PCM (sent to server)
- **Output**: 24kHz, mono, 16-bit PCM (received from server)
- **Binary framing**: First byte indicates source (0x01 client, 0x02 server)

### Session Protection

- 5-minute idle timeout (auto-disconnect)
- Configurable max session duration (default 12 minutes)
- 1-minute warning before disconnect

## Features

### Interview Prep Mode
- Role-specific interview practice (VP of People, CTO, Head of Marketing, Junior Engineer)
- AI-powered responses and feedback
- Session recording and analysis

### Language Test Mode (Admin only)
- English and Spanish language practice
- Fluency and grammar assessment
- Proficiency level evaluation

## Permissions

The app requires:
- **Microphone**: For voice-based interview sessions
- **Network**: To communicate with the backend API

## Troubleshooting

### WebSocket Connection Failed
- Ensure the backend server is running on `localhost:8001`
- Check that the interview ID is valid
- Verify network connectivity

### Audio Not Recording
- Check microphone permissions in Settings > Privacy > Microphone
- Ensure no other app is using the microphone
- Try restarting the app

### Token Expired
- The app will automatically attempt to refresh tokens
- If refresh fails, you'll be logged out and need to sign in again

## Development

### Adding New Features

1. Create models in `Models/`
2. Add API methods to `APIClient.swift`
3. Create or update ViewModels
4. Build UI in Views

### Running Tests

```bash
xcodebuild test -scheme MatchaTutor -destination 'platform=iOS Simulator,name=iPhone 14 Pro'
```

## License

Proprietary - Matcha Recruit

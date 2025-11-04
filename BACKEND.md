# FX Trading Backend - Knowledge Transfer Document

## Project Overview
This is a Django-based FX trading backend system with real-time market data processing, position management, and WebSocket support. The system handles live market data feeds, position tracking, margin calculations, and provides REST APIs for frontend integration.

## Project Structure & File Dependencies

### Core Django Configuration
**Priority: HIGH - Start here**

1. **core/settings.py** - Main Django configuration
   - Database: PostgreSQL
   - Redis: For caching and real-time data
   - CORS: Configured for frontend access
   - JWT: Authentication system
   - Channels: WebSocket support
   - External APIs: Alltick for market data

2. **core/urls.py** - URL routing configuration
   - API endpoints mapping
   - Authentication routes
   - Admin interface

3. **core/asgi.py** - ASGI configuration for WebSocket support

4. **core/wsgi.py** - WSGI configuration for HTTP requests

### Market Data Application Core
**Priority: HIGH - Core business logic**

5. **marketdata/models.py** - Database models
   - UserAccount: User financial data
   - Order: Trading orders
   - Fill: Executed trades
   - Position: Position tracking

6. **marketdata/contracts.py** - Trading specifications
   - SymbolSpec: Currency pair definitions
   - Contract sizes, leverage, precision
   - Trading hours and limits

7. **marketdata/serializers.py** - API serializers
   - OrderSerializer
   - FillSerializer

8. **marketdata/admin.py** - Django admin configuration

### Real-time Data Processing
**Priority: HIGH - Critical for live trading**

9. **marketdata/engine/redis_ops.py** - Redis operations
   - Position management
   - Fill processing with netting
   - Mark-to-market calculations
   - Position snapshots

10. **marketdata/engine/positions.py** - Position engine
    - Fill processing logic
    - Position updates
    - Real-time calculations

11. **marketdata/engine/margin_utils.py** - Margin calculations
    - Order validation
    - Margin requirements
    - Risk management

### WebSocket & Real-time Communication
**Priority: MEDIUM - Real-time features**

12. **marketdata/consumers.py** - WebSocket consumers
    - User-specific channels
    - Real-time position updates
    - Market data streaming

13. **marketdata/streams/user_ws.py** - User WebSocket handling
    - Connection management
    - Message routing

### External Data Integration
**Priority: MEDIUM - Market data feeds**

14. **marketdata/alltick_manager.py** - Alltick API integration
    - Market data fetching
    - Price feeds
    - Symbol metadata

15. **marketdata/pricing.py** - Price management
    - Price calculations
    - Spread handling

### API Endpoints
**Priority: HIGH - Frontend integration**

16. **marketdata/views.py** - REST API views
    - PositionsSnapshotView: Live position data
    - SimFillView: Simulate trades
    - ClosePositionView: Close positions
    - OrderListView: Order history
    - FillListView: Trade history
    - MarginCheckView: Margin validation
    - ExitPositionAPIView: Exit specific positions

### Management Commands
**Priority: LOW - Background tasks**

17. **marketdata/management/commands/run_positions_engine.py** - Position engine runner
18. **marketdata/management/commands/run_margin_updater.py** - Margin updater
19. **marketdata/management/commands/add_capital.py** - Add user capital
20. **marketdata/management/commands/delete_old_positions.py** - Cleanup old positions

### Database Migrations
**Priority: MEDIUM - Database schema**

21. **marketdata/migrations/** - Database migration files
    - Initial migrations
    - Schema updates

### Testing & Utilities
**Priority: LOW - Development support**

22. **marketdata/tests.py** - Unit tests
23. **marketdata/signals.py** - Django signals
24. **marketdata/apps.py** - App configuration

## Key Dependencies & External Services

### Database
- **PostgreSQL**: Primary database for persistent data
- **Redis**: Real-time data caching and position management

### External APIs
- **Alltick**: Market data provider
  - REST API: Historical data, symbols
  - WebSocket: Live price feeds

### Python Packages
- **Django**: Web framework
- **Django REST Framework**: API framework
- **Django Channels**: WebSocket support
- **django-cors-headers**: CORS handling
- **djangorestframework-simplejwt**: JWT authentication
- **channels-redis**: Redis channel layer
- **psycopg2**: PostgreSQL adapter
- **redis**: Redis client
- **requests**: HTTP client for external APIs

## Critical Business Logic Flow

### 1. Position Management
```
User places order → Order validation → Fill processing → Position update → Redis storage → WebSocket notification
```

### 2. Real-time Data Flow
```
Alltick WebSocket → Price processing → Mark-to-market → Position updates → User notifications
```

### 3. API Request Flow
```
Frontend request → JWT authentication → Business logic → Redis operations → Database updates → Response
```

## Configuration Requirements

### Environment Variables
- `REDIS_URL`: Redis connection string
- `ALLTICK_API_KEY`: Market data API key
- `ALLTICK_BASE_REST`: REST API endpoint
- `ALLTICK_BASE_WS`: WebSocket endpoint

### Database Setup
- PostgreSQL database: `postgres`
- User: `postgres`
- Password: `shahid`
- Host: `127.0.0.1:5432`

## Common Issues & Solutions

### CORS Errors
- Ensure `corsheaders` middleware is properly configured
- Check `CORS_ALLOW_ALL_ORIGINS = True` in settings
- Add explicit OPTIONS handling for complex requests

### Redis Connection Issues
- Verify Redis server is running
- Check `REDIS_URL` environment variable
- Ensure Redis is accessible from Django

### WebSocket Issues
- Verify Channels configuration
- Check Redis channel layer setup
- Ensure proper ASGI configuration

## Development Workflow

### Starting the System
1. Start PostgreSQL database
2. Start Redis server
3. Run migrations: `python manage.py migrate`
4. Start Django server: `python manage.py runserver`
5. Start position engine: `python manage.py run_positions_engine`

### Testing APIs
- Health check: `GET /health`
- Positions: `GET /api/positions/snapshot`
- Simulate fill: `POST /api/sim/fill`
- Close position: `POST /api/positions/close`

## Security Considerations

### Authentication
- JWT tokens for API access
- Token refresh mechanism
- User-specific data isolation

### Data Validation
- Input validation on all endpoints
- Margin checks before order execution
- Position size limits

### CORS Configuration
- Restricted origins in production
- Proper headers for preflight requests

## Performance Considerations

### Redis Usage
- Hot data in Redis for fast access
- Position snapshots for quick retrieval
- Real-time calculations

### Database Optimization
- Proper indexing on user_id fields
- Efficient queries for position data
- Transaction management for consistency

## Next Steps for New AI

1. **Start with core/settings.py** - Understand the complete configuration
2. **Review marketdata/models.py** - Understand data structures
3. **Study marketdata/engine/redis_ops.py** - Core business logic
4. **Examine marketdata/views.py** - API endpoints
5. **Check marketdata/consumers.py** - WebSocket handling
6. **Review marketdata/contracts.py** - Trading specifications

## File Reading Order for Complete Understanding

1. core/settings.py
2. core/urls.py
3. marketdata/models.py
4. marketdata/contracts.py
5. marketdata/engine/redis_ops.py
6. marketdata/engine/positions.py
7. marketdata/views.py
8. marketdata/consumers.py
9. marketdata/alltick_manager.py
10. marketdata/management/commands/run_positions_engine.py

This structure provides a complete roadmap for understanding the FX trading backend system.

"""
Database initialization script for TWS Robot.

This script:
1. Connects to the MySQL database using credentials from .env
2. Creates all necessary tables
3. Verifies the setup
4. Shows table information

Usage:
    python init_database.py
"""

import os
import sys
from dotenv import load_dotenv
import pymysql
from data.database import Database

def main():
    print("=" * 70)
    print("TWS Robot - Database Initialization")
    print("=" * 70)
    
    # Load environment variables
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL not found in .env file")
        print("\nPlease add your database URL to .env:")
        print("DATABASE_URL=mysql+pymysql://user:pass@host:port/database")
        sys.exit(1)
    
    # Mask password for display
    display_url = database_url
    if '@' in display_url and ':' in display_url:
        parts = display_url.split('@')
        cred_parts = parts[0].split('://')
        if len(cred_parts) > 1 and ':' in cred_parts[1]:
            user = cred_parts[1].split(':')[0]
            display_url = f"{cred_parts[0]}://{user}:****@{parts[1]}"
    
    print(f"\n📊 Database URL: {display_url}")
    print("\n" + "=" * 70)
    
    try:
        # Create database instance
        print("\n1️⃣  Connecting to database...")
        db = Database(database_url=database_url, echo=False)
        print("   ✅ Connected successfully!")
        
        # Create all tables
        print("\n2️⃣  Creating database tables...")
        db.create_tables()
        print("   ✅ Tables created successfully!")
        
        # Verify tables
        print("\n3️⃣  Verifying database setup...")
        with db.session_scope() as session:
            # Test by creating a default strategy
            from data.models import Strategy
            
            # Check if Manual Trading strategy exists
            existing = session.query(Strategy).filter_by(name="Manual Trading").first()
            
            if not existing:
                default_strategy = Strategy(
                    name="Manual Trading",
                    description="Default strategy for manual trades",
                    is_active=True,
                    config={"type": "manual", "risk_per_trade": 0.02}
                )
                session.add(default_strategy)
                print("   ✅ Created default 'Manual Trading' strategy")
            else:
                print("   ✅ Default 'Manual Trading' strategy already exists")
        
        print("\n4️⃣  Database Tables Summary:")
        print("   " + "-" * 66)
        tables = [
            ("strategies", "Strategy configuration and tracking"),
            ("trades", "Completed trade records with P&L"),
            ("positions", "Current and historical positions"),
            ("orders", "Order lifecycle tracking"),
            ("market_data", "Historical OHLCV bars"),
            ("performance_metrics", "Daily and cumulative performance")
        ]
        
        for table_name, description in tables:
            print(f"   ✅ {table_name:<25} - {description}")
        
        print("\n" + "=" * 70)
        print("🎉 Database initialization complete!")
        print("=" * 70)
        
        print("\n📝 Next Steps:")
        print("   1. The database is ready to use")
        print("   2. Start tws_client.py to begin trading")
        print("   3. All trades will be automatically saved to the database")
        print("\n" + "=" * 70 + "\n")
        
        # Close connection
        db.close()
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nPlease check:")
        print("  - Database credentials in .env are correct")
        print("  - Database server is accessible")
        print("  - pymysql package is installed: pip install pymysql")
        sys.exit(1)

if __name__ == "__main__":
    main()

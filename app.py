import streamlit as st
import pandas as pd
import sqlalchemy as db
import hashlib
from datetime import datetime
import matplotlib.pyplot as plt
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import subprocess
import os

# --- DATABASE SETUP ---
DB_FILE = "expenses.db"
engine = db.create_engine(f"sqlite:///{DB_FILE}")

# --- PASSWORD HASHING & USER AUTH ---
def make_hashes(password): return hashlib.sha256(str.encode(password)).hexdigest()
def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text: return hashed_text
    return False
def check_user_exists(username):
    with engine.connect() as conn:
        result = conn.execute(db.text("SELECT username FROM users WHERE username = :user"), {"user": username})
        return result.scalar() is not None
def add_userdata(username, password):
    with engine.connect() as conn:
        conn.execute(db.text("INSERT INTO users(username, password) VALUES(:user, :pass)"), {"user": username, "pass": make_hashes(password)})
        conn.commit()
def login_user(username, password):
    with engine.connect() as conn:
        result = conn.execute(db.text("SELECT password FROM users WHERE username = :user"), {"user": username})
        hashed_pass = result.scalar()
        if hashed_pass: return check_hashes(password, hashed_pass)
    return False

# --- EXPENSE MANAGEMENT ---
def add_expense(username, date, category, amount, description):
    with engine.connect() as conn:
        conn.execute(db.text("INSERT INTO expenses(username, expense_date, category, amount, description) VALUES(:user, :date, :cat, :amt, :desc)"),
                     {"user": username, "date": date, "cat": category, "amt": amount, "desc": description})
        conn.commit()
def view_all_expenses(username, is_admin=False):
    with engine.connect() as conn:
        if is_admin:
            query = "SELECT id, username, expense_date, category, amount, description FROM expenses"
            df = pd.read_sql(query, conn)
        else:
            query = "SELECT id, expense_date, category, amount, description FROM expenses WHERE username = :user"
            df = pd.read_sql(query, conn, params={"user": username})
    return df
def delete_data(expense_id):
    with engine.connect() as conn:
        conn.execute(db.text("DELETE FROM expenses WHERE id=:id"), {"id": expense_id})
        conn.commit()

# --- GOAL & BADGE MANAGEMENT ---
def create_goal(username, goal_name, target_amount, image_url):
    with engine.connect() as conn:
        conn.execute(db.text("INSERT INTO goals(username, goal_name, target_amount, image_url) VALUES(:user, :name, :target, :url)"),
                     {"user": username, "name": goal_name, "target": target_amount, "url": image_url}); conn.commit()
def get_user_goals(username):
    with engine.connect() as conn:
        return pd.read_sql("SELECT * FROM goals WHERE username = :user", conn, params={"user": username})
def add_to_goal(goal_id, amount_to_add):
    with engine.connect() as conn:
        conn.execute(db.text("UPDATE goals SET current_amount = current_amount + :amount WHERE id = :id"),
                     {"amount": amount_to_add, "id": goal_id}); conn.commit()
def delete_goal(goal_id):
     with engine.connect() as conn:
        conn.execute(db.text("DELETE FROM goals WHERE id=:id"), {"id": goal_id}); conn.commit()
BADGES = {
    "First Expense": "Log your very first expense.", "Budget Starter": "Log 5 expenses.",
    "Consistent Tracker": "Log 15 expenses.", "Goal Setter": "Create your first savings goal.",
    "Super Saver": "Save over ₹10,000 across all goals."
}
def get_user_badges(username):
    with engine.connect() as conn:
        result = conn.execute(db.text("SELECT badge_name FROM badges WHERE username = :user"), {"user": username})
        return [row[0] for row in result]
def award_badge(username, badge_name):
    with engine.connect() as conn:
        try:
            conn.execute(db.text("INSERT INTO badges(username, badge_name, date_unlocked) VALUES(:user, :badge, :date)"),
                         {"user": username, "badge": badge_name, "date": datetime.now().date()}); conn.commit()
            st.toast(f"🏆 Achievement Unlocked: {badge_name}!", icon="🎉")
        except Exception: pass
def check_and_award_badges(username):
    num_expenses = len(view_all_expenses(username))
    if num_expenses >= 1: award_badge(username, "First Expense")
    if num_expenses >= 5: award_badge(username, "Budget Starter")
    if num_expenses >= 15: award_badge(username, "Consistent Tracker")
    df_goals = get_user_goals(username)
    if not df_goals.empty: award_badge(username, "Goal Setter")
    if not df_goals.empty and df_goals['current_amount'].sum() >= 10000: award_badge(username, "Super Saver")

# --- AI SMART INSIGHTS FUNCTION ---
def generate_smart_insights(username):
    df = view_all_expenses(username)
    insights = []
    if len(df) < 5: return ["Keep logging your expenses to unlock smart insights!"]
    df['expense_date'] = pd.to_datetime(df['expense_date'])
    today = datetime.now()
    current_month_start = today.replace(day=1)
    last_month_end = current_month_start - pd.Timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    df_current = df[df['expense_date'] >= pd.to_datetime(current_month_start.date())]
    df_last = df[(df['expense_date'] >= pd.to_datetime(last_month_start.date())) & (df['expense_date'] <= pd.to_datetime(last_month_end.date()))]
    if df_current.empty or df_last.empty: return ["Not enough data for a monthly comparison yet. Keep tracking!"]
    current_top_cat_series = df_current.groupby('category')['amount'].sum()
    if not current_top_cat_series.empty:
        current_top_cat = current_top_cat_series.idxmax()
        current_spend = current_top_cat_series.max()
        last_spend_series = df_last.groupby('category')['amount'].sum()
        last_spend = last_spend_series.get(current_top_cat, 0)
        if current_spend > last_spend * 1.2 and last_spend > 0:
            insights.append(f"💡 Heads up! Your spending on '{current_top_cat}' is ₹{current_spend:,.0f} so far, higher than all of last month (₹{last_spend:,.0f}).")
        elif current_spend < last_spend:
             insights.append(f"👍 Great job! You've spent less on '{current_top_cat}' this month (₹{current_spend:,.0f}) compared to last month (₹{last_spend:,.0f}).")
    total_current = df_current['amount'].sum()
    total_last = df_last['amount'].sum()
    if total_current > total_last:
        insights.append(f"📈 Your total spending this month (₹{total_current:,.0f}) is trending higher than last month (₹{total_last:,.0f}).")
    return insights if insights else ["Your spending is consistent with last month. Keep it up!"]

# --- STREAMLIT APP ---
def main():
    st.set_page_config(page_title="QuestFinance", page_icon="🚀")
    st.title("🚀 QuestFinance: Level Up Your Savings")
    if not os.path.exists(DB_FILE):
        subprocess.run(['python', 'create_db.py'], check=True)
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False; st.session_state.username = ''; st.session_state.is_admin = False
    if not st.session_state.logged_in:
        choice = st.selectbox("Login or Sign Up", ["Login", "Sign Up"])
        if choice == "Login":
            st.subheader("Login Section")
            username = st.text_input("Username"); password = st.text_input("Password", type='password')
            if st.button("Login"):
                if login_user(username, password):
                    st.session_state.logged_in = True; st.session_state.username = username
                    st.session_state.is_admin = (username == 'Itachibanker19')
                    st.success(f"Welcome {username}"); st.rerun()
                else: st.warning("Incorrect Username/Password")
        else:
            st.subheader("Create a New Account")
            new_username = st.text_input("Username"); new_password = st.text_input("Password", type='password')
            confirm_password = st.text_input("Confirm Password", type='password')
            if st.button("Sign Up"):
                if new_password == confirm_password:
                    if not check_user_exists(new_username):
                        add_userdata(new_username, new_password); st.success("Account created successfully!"); st.info("You can now log in.")
                    else: st.error("That username is already taken.")
                else: st.warning("Passwords do not match.")
    else:
        username = st.session_state.username
        check_and_award_badges(username)
        st.sidebar.subheader(f"Welcome {username}")
        menu = ["Add Expense", "Summary", "Manage Records", "Goals & Achievements"]
        choice = st.sidebar.selectbox("Menu", menu)
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False; st.session_state.username = ''; st.session_state.is_admin = False; st.rerun()

        if choice == "Add Expense":
            st.subheader("Add a New Expense")
            with st.form("expense_form", clear_on_submit=True):
                expense_date = st.date_input("Date", datetime.now()); category = st.selectbox("Category", ["Food", "Transport", "Shopping", "Bills", "Entertainment", "Other"])
                amount = st.number_input("Amount", min_value=0.01, format="%.2f"); description = st.text_area("Description")
                if st.form_submit_button("Add Expense"):
                    add_expense(username, expense_date, category, amount, description); st.success("Expense added!")

        elif choice == "Summary":
            st.subheader("Expense Summary")
            st.markdown("### 🤖 Smart Insights"); insights = generate_smart_insights(username)
            for insight in insights: st.info(insight)
            st.markdown("---")
            df = view_all_expenses(username, st.session_state.is_admin)
            if not df.empty: st.dataframe(df)
            else: st.info("No expenses recorded yet.")
        
        elif choice == "Manage Records":
             st.subheader("Manage Your Expenses"); df = view_all_expenses(st.session_state.username, st.session_state.is_admin)
             if not df.empty:
                st.dataframe(df)
                expense_ids = df['id'].tolist()
                selected_id = st.selectbox("Select Expense ID to Delete", expense_ids)
                if selected_id and st.button("Delete", key=f"delete_{selected_id}", type="primary"):
                    delete_data(selected_id); st.success(f"Deleted record ID: {selected_id}"); st.rerun()
             else: st.info("No records to manage.")

        elif choice == "Goals & Achievements":
            st.subheader("🎯 Your Goals & Achievements")
            st.markdown("### 🏆 Savings Goals")
            goals_df = get_user_goals(username)
            if not goals_df.empty:
                for index, row in goals_df.iterrows():
                    goal_id, _, name, target, current, img_url = row
                    progress = (current / target) * 100 if target > 0 else 0
                    st.markdown(f"**{name}**"); st.progress(int(progress)); st.text(f"₹{int(current):,} / ₹{int(target):,}")
                    with st.form(key=f"goal_{goal_id}"):
                        amount_to_add = st.number_input("Add to this goal", min_value=1.0, step=100.0, format="%.2f")
                        if st.form_submit_button("Add Savings"):
                            add_to_goal(goal_id, amount_to_add); st.success(f"Added ₹{amount_to_add} to {name}!"); st.rerun()
                    if st.button(f"Delete Goal: {name}", key=f"del_goal_{goal_id}"):
                         delete_goal(goal_id); st.rerun()
                    st.markdown("---")
            with st.expander("Create a New Goal"):
                with st.form("new_goal_form", clear_on_submit=True):
                    goal_name = st.text_input("Goal Name"); target_amount = st.number_input("Target Amount", min_value=1.0)
                    image_url = st.text_input("Image URL (optional)")
                    if st.form_submit_button("Set Goal"):
                        create_goal(username, goal_name, target_amount, image_url); st.success("New goal created!"); st.rerun()
            st.markdown("---"); st.markdown("### 🏅 Achievements")
            unlocked_badges = get_user_badges(username)
            cols = st.columns(4)
            for i, (badge, desc) in enumerate(BADGES.items()):
                with cols[i % 4]:
                    if badge in unlocked_badges: st.success(f"**{badge}**", icon="🏆"); st.caption(desc)
                    else: st.info(f"**{badge}** (Locked)", icon="🔒")

if __name__ == '__main__':
    main()


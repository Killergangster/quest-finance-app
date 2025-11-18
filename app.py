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
def get_all_usernames(current_user):
    with engine.connect() as conn:
        result = conn.execute(db.text("SELECT username FROM users WHERE username != :user"), {"user": current_user})
        return [row[0] for row in result]

# --- EXPENSE MANAGEMENT (CRUD) ---
def add_expense(username, date, category, amount, description):
    with engine.connect() as conn:
        # Returns the ID of the new expense (needed for debts)
        result = conn.execute(db.text("INSERT INTO expenses(username, expense_date, category, amount, description) VALUES(:user, :date, :cat, :amt, :desc) RETURNING id"),
                     {"user": username, "date": date, "cat": category, "amt": amount, "desc": description})
        new_id = result.scalar()
        conn.commit()
        return new_id

def view_all_expenses(username, is_admin=False):
    with engine.connect() as conn:
        if is_admin:
            query = "SELECT id, username, expense_date, category, amount, description FROM expenses"
            df = pd.read_sql(query, conn)
        else:
            query = "SELECT id, expense_date, category, amount, description FROM expenses WHERE username = :user"
            df = pd.read_sql(query, conn, params={"user": username})
    return df

def get_expense_by_id(expense_id):
    with engine.connect() as conn:
        result = conn.execute(db.text("SELECT * FROM expenses WHERE id = :id"), {"id": expense_id})
        return result.first()

def edit_expense_data(expense_id, date, category, amount, description):
    with engine.connect() as conn:
        conn.execute(db.text("UPDATE expenses SET expense_date=:date, category=:cat, amount=:amt, description=:desc WHERE id=:id"),
                     {"date": date, "cat": category, "amt": amount, "desc": description, "id": expense_id})
        conn.commit()

def delete_data(expense_id):
    with engine.connect() as conn:
        # Delete associated debts first to avoid database errors
        conn.execute(db.text("DELETE FROM debts WHERE expense_id=:id"), {"id": expense_id})
        conn.execute(db.text("DELETE FROM expenses WHERE id=:id"), {"id": expense_id})
        conn.commit()

# --- SOCIAL DEBT SPLITTING ---
def create_debt(expense_id, payer, owes_list, split_amount):
    with engine.connect() as conn:
        for user in owes_list:
            conn.execute(db.text("INSERT INTO debts(expense_id, payer_username, owes_username, amount) VALUES(:exp_id, :payer, :owes, :amt)"),
                         {"exp_id": expense_id, "payer": payer, "owes": user, "amt": split_amount})
        conn.commit()

def get_user_debts(username):
    with engine.connect() as conn:
        you_owe_df = pd.read_sql("SELECT id, payer_username, amount FROM debts WHERE owes_username = :user AND status = 'unpaid'", conn, params={"user": username})
        you_are_owed_df = pd.read_sql("SELECT id, owes_username, amount FROM debts WHERE payer_username = :user AND status = 'unpaid'", conn, params={"user": username})
    return you_owe_df, you_are_owed_df

def settle_debt(debt_id):
    with engine.connect() as conn:
        conn.execute(db.text("UPDATE debts SET status = 'paid' WHERE id = :id"), {"id": debt_id})
        conn.commit()

# --- DATA VISUALIZATION ---
def plot_expenses_by_category(df):
    if df.empty: return None
    category_summary = df.groupby('category')['amount'].sum()
    fig, ax = plt.subplots()
    category_summary.plot(kind='pie', ax=ax, autopct='%1.1f%%', startangle=90)
    ax.set_ylabel('')
    ax.set_title("Expenses by Category")
    return fig

def plot_expenses_over_time(df):
    if df.empty: return None
    df['expense_date'] = pd.to_datetime(df['expense_date'])
    time_summary = df.set_index('expense_date').resample('M')['amount'].sum()
    fig, ax = plt.subplots()
    time_summary.plot(kind='line', ax=ax, marker='o')
    ax.set_title("Monthly Spending Trend")
    ax.set_xlabel("Month")
    ax.set_ylabel("Amount")
    plt.grid(True)
    return fig

def plot_bar_chart_by_category(df):
    if df.empty: return None
    category_summary = df.groupby('category')['amount'].sum().sort_values(ascending=False)
    fig, ax = plt.subplots()
    category_summary.plot(kind='bar', ax=ax)
    ax.set_title("Spending per Category")
    ax.set_xlabel("Category")
    plt.xticks(rotation=45, ha='right')
    return fig

# --- EXPORT FUNCTIONS ---
def export_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Expenses')
    return output.getvalue()

def export_to_pdf(df, username, is_admin=False):
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter)
    elements, styles = [], getSampleStyleSheet()
    title = f"Expense Report for {username}" if not is_admin else "Full Company Expense Report"
    elements.append(Paragraph(title, styles['h1']))
    df_list = [df.columns.values.tolist()] + df.values.tolist()
    table = Table(df_list)
    style = TableStyle([('BACKGROUND', (0,0), (-1,0), colors.grey), ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0,0), (-1,0), 12), ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                        ('GRID', (0,0), (-1,-1), 1, colors.black)])
    table.setStyle(style)
    elements.append(table)
    doc.build(elements)
    return output.getvalue()

# --- GAMIFICATION ---
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

# --- AI SMART INSIGHTS ---
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
        # --- LOGGED IN INTERFACE ---
        username = st.session_state.username
        check_and_award_badges(username)

        st.sidebar.subheader(f"Welcome {username}")
        # Updated Menu with "Debts"
        menu = ["Add Expense", "Debts", "Summary", "Manage Records", "Goals & Achievements"]
        choice = st.sidebar.selectbox("Menu", menu)

        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False; st.session_state.username = ''; st.session_state.is_admin = False; st.rerun()

        if choice == "Add Expense":
            st.subheader("Add a New Expense")
            with st.form("expense_form", clear_on_submit=True):
                expense_date = st.date_input("Date", datetime.now())
                category = st.selectbox("Category", ["Food", "Transport", "Shopping", "Bills", "Entertainment", "Other"])
                amount = st.number_input("Amount", min_value=0.01, format="%.2f")
                description = st.text_area("Description")
                
                # --- SPLIT BILL FEATURE ---
                st.markdown("---")
                st.markdown("💸 **Split this Bill?**")
                all_users = get_all_usernames(username)
                split_with = st.multiselect("Select friends to split with:", all_users)
                # -------------------------

                if st.form_submit_button("Add Expense"):
                    new_id = add_expense(username, expense_date, category, amount, description)
                    
                    # Logic for split
                    if split_with:
                        num_people = len(split_with) + 1 # +1 is the payer
                        split_amount = round(amount / num_people, 2)
                        create_debt(new_id, username, split_with, split_amount)
                        st.success(f"Expense added and split! Each person owes ₹{split_amount}.")
                    else:
                        st.success("Expense added successfully!")

        elif choice == "Debts":
            st.subheader("💸 Your Debt Ledger")
            st.info("Track money you owe and money owed to you.")
            you_owe, you_are_owed = get_user_debts(username)
            
            c1, c2 = st.columns(2)
            c1.metric("You Owe", f"₹{you_owe['amount'].sum():,.2f}", delta_color="inverse")
            c2.metric("Owed to You", f"₹{you_are_owed['amount'].sum():,.2f}")

            st.markdown("---")
            st.write("#### People You Owe")
            if not you_owe.empty:
                for i, row in you_owe.iterrows():
                    col1, col2, col3 = st.columns([2,2,1])
                    col1.text(f"To: {row['payer_username']}")
                    col2.text(f"Amount: ₹{row['amount']}")
                    if col3.button("Pay", key=f"pay_{row['id']}"):
                        settle_debt(row['id']); st.success("Paid!"); st.rerun()
            else: st.info("You are debt free!")
            
            st.markdown("---")
            st.write("#### People Who Owe You")
            if not you_are_owed.empty:
                st.dataframe(you_are_owed)
            else: st.info("No one owes you money.")


        elif choice == "Summary":
            st.subheader("Expense Summary")
            st.markdown("### 🤖 Smart Insights"); insights = generate_smart_insights(username)
            for insight in insights: st.info(insight)
            
            st.markdown("---")
            df = view_all_expenses(username, st.session_state.is_admin)
            if not df.empty:
                st.dataframe(df)
                # --- VISUALIZATIONS ---
                col1, col2 = st.columns(2)
                with col1: st.pyplot(plot_expenses_by_category(df))
                with col2: st.pyplot(plot_bar_chart_by_category(df))
                st.pyplot(plot_expenses_over_time(df))
            else: st.info("No expenses recorded yet.")
        
        elif choice == "Manage Records":
             st.subheader("Manage Your Expenses")
             df = view_all_expenses(st.session_state.username, st.session_state.is_admin)
             if not df.empty:
                st.dataframe(df)
                
                # --- EXPORT BUTTONS ---
                st.markdown("### Export Data")
                c1, c2 = st.columns(2)
                with c1:
                    st.download_button(label="📥 Export to Excel", data=export_to_excel(df), file_name="expenses.xlsx")
                with c2:
                    st.download_button(label="📄 Export to PDF", data=export_to_pdf(df, username, st.session_state.is_admin), file_name="report.pdf")

                # --- EDIT / DELETE ---
                st.markdown("### Edit or Delete")
                expense_ids = df['id'].tolist()
                selected_id = st.selectbox("Select Expense ID", expense_ids)
                
                if selected_id:
                    c1, c2 = st.columns(2)
                    if c1.button("Edit"): st.session_state.edit_id = selected_id
                    if c2.button("Delete", type="primary"): 
                        delete_data(selected_id); st.success("Deleted!"); st.rerun()
                    
                    # Edit Form logic
                    if 'edit_id' in st.session_state and st.session_state.edit_id == selected_id:
                        expense = get_expense_by_id(selected_id)
                        with st.form("edit_form"):
                            new_date = st.date_input("Date", pd.to_datetime(expense.expense_date))
                            new_cat = st.selectbox("Category", ["Food", "Transport", "Shopping", "Bills", "Entertainment", "Other"], index=["Food", "Transport", "Shopping", "Bills", "Entertainment", "Other"].index(expense.category))
                            new_amt = st.number_input("Amount", value=expense.amount)
                            new_desc = st.text_area("Description", value=expense.description)
                            if st.form_submit_button("Save Changes"):
                                edit_expense_data(selected_id, new_date, new_cat, new_amt, new_desc)
                                st.success("Updated!"); del st.session_state.edit_id; st.rerun()

             else: st.info("No records to manage.")

        elif choice == "Goals & Achievements":
            st.subheader("🎯 Goals & Achievements")
            st.markdown("### 🏆 Savings Goals")
            goals_df = get_user_goals(username)
            if not goals_df.empty:
                for index, row in goals_df.iterrows():
                    goal_id, name, target, current = row['id'], row['goal_name'], row['target_amount'], row['current_amount']
                    progress = (current / target) * 100 if target > 0 else 0
                    st.markdown(f"**{name}**"); st.progress(min(int(progress), 100)); st.text(f"₹{int(current):,} / ₹{int(target):,}")
                    with st.form(key=f"goal_{goal_id}"):
                        amt = st.number_input("Add Savings", min_value=1.0, key=f"amt_{goal_id}")
                        if st.form_submit_button("Add"): add_to_goal(goal_id, amt); st.rerun()
                    if st.button("Delete Goal", key=f"del_{goal_id}"): delete_goal(goal_id); st.rerun()
                    st.markdown("---")
            
            with st.expander("Create New Goal"):
                with st.form("new_goal"):
                    g_name = st.text_input("Goal Name")
                    g_target = st.number_input("Target Amount")
                    if st.form_submit_button("Create"): create_goal(username, g_name, g_target, ""); st.rerun()

            st.markdown("### 🏅 Achievements")
            badges = get_user_badges(username)
            cols = st.columns(4)
            for i, (b_name, b_desc) in enumerate(BADGES.items()):
                with cols[i % 4]:
                    if b_name in badges: st.success(f"**{b_name}**\n\n{b_desc}")
                    else: st.info(f"**{b_name}**\n\nLocked")

if __name__ == '__main__':
    main()

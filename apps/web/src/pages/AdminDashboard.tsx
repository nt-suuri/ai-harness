import React from "react";

export default function AdminDashboard() {
  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>Admin Dashboard</h1>
      </header>
      <main style={styles.main}>
        <p style={styles.info}>Welcome to the enhanced admin dashboard. Stay tuned for more updates!</p>
      </main>
    </div>
  );
}

const styles = {
  container: {
    fontFamily: 'Arial, sans-serif',
    margin: '0',
    padding: '0',
    backgroundColor: '#f9f9f9',
    height: '100vh'
  },
  header: {
    backgroundColor: '#4CAF50',
    color: '#fff',
    padding: '10px 20px',
    textAlign: 'center'
  },
  title: {
    margin: '0',
    fontSize: '24px'
  },
  main: {
    padding: '20px',
    textAlign: 'center'
  },
  info: {
    color: '#555',
    fontSize: '18px'
  }
};
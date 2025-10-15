<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Update Vital Signs</title>
  <!-- Supabase JS client is not used directly; backend handles DB I/O -->

  <style>
    body {
      background-color: #f0f8ff;
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 0;
    }
    .container {
      max-width: 900px;
      margin: 40px auto;
      background: white;
      padding: 20px 30px;
      border-radius: 12px;
      box-shadow: 0 0 12px rgba(0, 0, 0, 0.2);
    }
    h2 {
      text-align: center;
      color: #003366;
    }
    label {
      display: block;
      margin-top: 12px;
      font-weight: bold;
      text-align: left;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    input[type="text"],
    input[type="number"],
    input[type="date"],
    input[type="time"],
    textarea {
      width: 100%;
      padding: 10px;
      margin-top: 4px;
      font-size: 16px;
      border: 1px solid #ccc;
      border-radius: 6px;
      box-sizing: border-box;
    }
    button {
      background-color: #0066cc;
      color: white;
      border: none;
      padding: 10px 16px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 16px;
      margin-top: 16px;
    }
    button:hover {
      background-color: #004999;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 24px;
    }
    th, td {
      border: 1px solid #ccc;
      padding: 10px;
      text-align: left;
    }
    th {
      background-color: #e0eaff;
    }
    .top-right {
      text-align: right;
      margin-bottom: 10px;
    }
    .status-message {
      margin-top: 15px;
      padding: 10px;
      border-radius: 5px;
      font-weight: bold;
      text-align: center;
    }
    .status-message.success {
      background-color: #d4edda;
      color: #155724;
      border: 1px solid #c3e6cb;
    }
    .status-message.error {
      background-color: #f8d7da;
      color: #721c24;
      border: 1px solid #f5c6cb;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="top-right">
      <button onclick="window.location.href='index.html'">⬅️ Return to Main Menu</button>
    </div>

    <h2>Update Vital Signs</h2>

    <form id="vitalSignsForm">
      <div class="row">
        <div>
          <label for="recordedDate">Date of Reading:</label>
          <input type="date" id="recordedDate" required>
        </div>
        <div>
          <label for="recordedTime">Time recorded:</label>
          <input type="time" id="recordedTime" required>
        </div>
      </div>

      <div class="row">
        <div>
          <label for="avgWeight">Average Weight (lbs):</label>
          <input type="number" id="avgWeight" step="0.1" placeholder="e.g., 150.5">
        </div>
        <div>
          <label for="avgGlucose">Average Glucose (mg/dL):</label>
          <input type="number" id="avgGlucose" step="0.1" placeholder="e.g., 95.2">
        </div>
      </div>

      <div class="row">
        <div>
          <label for="avgSystolic">Average Systolic BP (mmHg):</label>
          <input type="number" id="avgSystolic" step="1" placeholder="e.g., 120">
        </div>
        <div>
          <label for="avgDiastolic">Average Diastolic BP (mmHg):</label>
          <input type="number" id="avgDiastolic" step="1" placeholder="e.g., 80">
        </div>
      </div>

      <div class="row">
        <div>
          <label for="avgOxygen">Average Oxygen Saturation (%):</label>
          <input type="number" id="avgOxygen" step="0.1" placeholder="e.g., 98.5">
        </div>
        <div>
          <label for="heartRate">Heart rate (bpm):</label>
          <input type="number" id="heartRate" step="1" placeholder="e.g., 72">
        </div>
      </div>

      <label for="notes">Notes:</label>
      <textarea id="notes" rows="3" placeholder="Any additional comments about these readings"></textarea>

      <button type="submit">💾 Update Vital Signs</button>
    </form>

    <div id="formStatus" class="status-message" style="display: none;"></div>

    <h3>Previous Vital Signs</h3>
    <table id="vitalSignsTable">
      <thead>
        <tr>
          <th>Date / Time</th>
          <th>Weight (lbs)</th>
          <th>Glucose (mg/dL)</th>
          <th>BP (mmHg)</th>
          <th>O2 Sat (%)</th>
          <th>Heart Rate (bpm)</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <script>
    const patientId = localStorage.getItem('patientUUID');
    const formStatusDiv = document.getElementById('formStatus');
    const BACKEND_URL = 'https://seniors-meds-2.onrender.com';

    function showStatus(message, isError = false) {
      formStatusDiv.textContent = message;
      formStatusDiv.className = `status-message ${isError ? 'error' : 'success'}`;
      formStatusDiv.style.display = 'block';
      setTimeout(() => {
        formStatusDiv.style.display = 'none';
      }, 5000);
    }

    function toDisplayDateTime(recorded_at) {
      if (!recorded_at) return '';
      try {
        // Accepts values like "2025-10-15T13:45" or full ISO
        const d = new Date(recorded_at);
        if (isNaN(d.getTime())) return recorded_at; // fallback
        const date = d.toLocaleDateString();
        const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return `${date} ${time}`;
      } catch {
        return recorded_at;
      }
    }

    async function loadVitalSigns() {
      if (!patientId) {
        showStatus("Patient ID not found. Please log in.", true);
        return;
      }

      try {
        const res = await fetch(`${BACKEND_URL}/vital-signs/${patientId}`, {
          method: "GET",
          headers: { "Content-Type": "application/json" }
        });
        const result = await res.json();

        if (res.ok && result.success) {
          const tbody = document.querySelector('#vitalSignsTable tbody');
          tbody.innerHTML = '';

          result.data.forEach(entry => {
            const row = document.createElement('tr');
            const bp = (entry.average_systolic !== null && entry.average_diastolic !== null)
              ? `${entry.average_systolic}/${entry.average_diastolic}` : '';
            const dt = toDisplayDateTime(entry.recorded_at);

            row.innerHTML = `
              <td>${dt}</td>
              <td>${entry.average_weight ?? ''}</td>
              <td>${entry.average_glucose ?? ''}</td>
              <td>${bp}</td>
              <td>${entry.average_oxygen ?? ''}</td>
              <td>${entry.heart_rate ?? ''}</td>
              <td>${entry.notes || ''}</td>
            `;
            tbody.appendChild(row);
          });
        } else {
          showStatus("Error loading vital signs: " + (result.error || "Unknown error"), true);
          console.log("Error loading vital signs:", result);
        }
      } catch (err) {
        showStatus("Error contacting vital signs server.", true);
        console.log("Network error loading vital signs:", err);
      }
    }

    document.getElementById('vitalSignsForm').addEventListener('submit', async (e) => {
      e.preventDefault();

      if (!patientId) {
        showStatus("Patient ID not found. Please log in.", true);
        return;
      }

      const recordedDate = document.getElementById('recordedDate').value;
      const recordedTime = document.getElementById('recordedTime').value;
      const avgWeight = document.getElementById('avgWeight').value;
      const avgGlucose = document.getElementById('avgGlucose').value;
      const avgSystolic = document.getElementById('avgSystolic').value;
      const avgDiastolic = document.getElementById('avgDiastolic').value;
      const avgOxygen = document.getElementById('avgOxygen').value;
      const heartRate = document.getElementById('heartRate').value;
      const notes = document.getElementById('notes').value;

      if (!recordedDate) {
        showStatus("Please enter a date for the reading.", true);
        return;
      }
      if (!recordedTime) {
        showStatus("Please enter the time recorded.", true);
        return;
      }

      // Combine date and time; keep it simple for backend parsing.
      // Example: "2025-10-15T13:45"
      const recorded_at = `${recordedDate}T${recordedTime}`;

      const payload = {
        patient_id: patientId,
        recorded_at: recorded_at,
        average_weight: avgWeight !== '' ? parseFloat(avgWeight) : null,
        average_glucose: avgGlucose !== '' ? parseFloat(avgGlucose) : null,
        average_systolic: avgSystolic !== '' ? parseInt(avgSystolic, 10) : null,
        average_diastolic: avgDiastolic !== '' ? parseInt(avgDiastolic, 10) : null,
        average_oxygen: avgOxygen !== '' ? parseFloat(avgOxygen) : null,
        heart_rate: heartRate !== '' ? parseInt(heartRate, 10) : null,
        notes: notes !== '' ? notes : null
      };

      try {
        const res = await fetch(`${BACKEND_URL}/vital-signs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();

        if (res.ok && result.success) {
          showStatus('Vital signs saved successfully!', false);
          document.getElementById('vitalSignsForm').reset();
          loadVitalSigns();
        } else {
          showStatus('Error saving vital signs: ' + (result.error || 'Unknown error'), true);
          console.log("Error saving vital signs:", result);
        }
      } catch (err) {
        showStatus('Error contacting vital signs server.', true);
        console.log("Network error saving vital signs:", err);
      }
    });

    // Initial load
    loadVitalSigns();
  </script>
</body>
</html>

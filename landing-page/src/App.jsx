import React, { useState } from "react";

function App() {
  const [view, setView] = useState("landing"); // landing, auth, role
  const [authMode, setAuthMode] = useState("login"); // login, signup

  // Redirects to Streamlit with parameters
  const redirectToStreamlit = (role) => {
    const token = "mock_jwt_token_12345";
    window.location.href = `http://localhost:8501/?token=${token}&role=${encodeURIComponent(role)}`;
  };

  const renderLanding = () => (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col">
      {/* Header */}
      <header className="flex justify-between items-center p-6 bg-white border-b border-slate-200">
        <h1 className="text-2xl font-bold text-medical-deep tracking-tight">
          FichaClara
        </h1>
        <button
          onClick={() => {
            setAuthMode("login");
            setView("auth");
          }}
          className="text-medical-primary font-medium hover:text-medical-deep"
        >
          Iniciar sesión
        </button>
      </header>

      {/* Hero */}
      <main className="flex-grow flex flex-col items-center justify-center p-8 text-center">
        <h2 className="text-5xl font-bold text-medical-deep mb-6 max-w-3xl">
          Medication information you can understand and verify.
        </h2>
        <p className="text-lg text-slate-500 mb-10 max-w-2xl">
          FichaClara answers questions using strictly indexed official
          medication documentation (AEMPS/CIMA). Every answer provides
          transparent, verifiable sources.
        </p>
        <button
          onClick={() => {
            setAuthMode("signup");
            setView("auth");
          }}
          className="bg-medical-primary text-white px-8 py-4 rounded-md font-semibold text-lg hover:bg-blue-700 transition shadow-lg"
        >
          Start with FichaClara
        </button>

        {/* 3 Steps */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-24 max-w-5xl w-full text-left">
          <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
            <h3 className="font-bold text-xl text-medical-deep mb-2">
              01 Pregunta
            </h3>
            <p className="text-slate-600">
              Formula dudas en lenguaje natural sobre cualquier medicamento.
            </p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-sm border border-slate-200">
            <h3 className="font-bold text-xl text-medical-deep mb-2">
              02 Recupera
            </h3>
            <p className="text-slate-600">
              Búsqueda exclusiva en la documentación oficial indexada sin
              alucinaciones.
            </p>
          </div>
          <div className="bg-white p-6 rounded-lg shadow-sm border-t-4 border-t-medical-teal border-slate-200">
            <h3 className="font-bold text-xl text-medical-deep mb-2">
              03 Verifica
            </h3>
            <p className="text-slate-600">
              Comprueba la fuente exacta, la página y abre el enlace de CIMA.
            </p>
          </div>
        </div>
      </main>
    </div>
  );

  const renderAuth = () => (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="bg-white p-8 rounded-lg shadow-md border border-slate-200 max-w-md w-full">
        <h2 className="text-2xl font-bold text-medical-deep text-center mb-6">
          {authMode === "signup" ? "Crear cuenta" : "Iniciar sesión"}
        </h2>
        <input
          type="email"
          placeholder="Correo electrónico"
          className="w-full p-3 mb-4 border border-slate-300 rounded focus:outline-none focus:border-medical-primary"
        />
        <input
          type="password"
          placeholder="Contraseña"
          className="w-full p-3 mb-6 border border-slate-300 rounded focus:outline-none focus:border-medical-primary"
        />

        <button
          onClick={() => setView("role")}
          className="w-full bg-medical-primary text-white py-3 rounded font-medium hover:bg-blue-700 transition"
        >
          {authMode === "signup" ? "Registrarse" : "Entrar"}
        </button>

        <div className="mt-6 text-center text-sm text-slate-500">
          {authMode === "signup"
            ? "¿Ya tienes cuenta? "
            : "¿No tienes cuenta? "}
          <button
            onClick={() =>
              setAuthMode(authMode === "signup" ? "login" : "signup")
            }
            className="text-medical-primary font-medium"
          >
            {authMode === "signup" ? "Inicia sesión" : "Regístrate"}
          </button>
        </div>
      </div>
    </div>
  );

  const renderRoleSelection = () => {
    const roles = [
      {
        title: "Profesional Sanitario",
        desc: "Médicos, farmacéuticos, enfermería...",
      },
      { title: "Estudiante", desc: "Estudiantes de ciencias de la salud..." },
      {
        title: "Paciente / General",
        desc: "Búsqueda general de información...",
      },
      {
        title: "Investigador / Org",
        desc: "Análisis e investigación documental...",
      },
    ];

    return (
      <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4">
        <div className="max-w-4xl w-full">
          <h2 className="text-3xl font-bold text-medical-deep text-center mb-2">
            How will you use FichaClara?
          </h2>
          <p className="text-center text-slate-500 mb-10">
            Selecciona tu perfil para adaptar tu espacio de trabajo. Las reglas
            de seguridad clínica se mantienen para todos.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {roles.map((role, idx) => (
              <button
                key={idx}
                onClick={() => redirectToStreamlit(role.title)}
                className="bg-white p-6 rounded-lg border border-slate-200 shadow-sm hover:border-medical-primary hover:shadow-md transition text-left flex flex-col items-start"
              >
                <h4 className="text-xl font-bold text-medical-primary mb-1">
                  {role.title}
                </h4>
                <p className="text-slate-500 text-sm">{role.desc}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      {view === "landing" && renderLanding()}
      {view === "auth" && renderAuth()}
      {view === "role" && renderRoleSelection()}
    </>
  );
}

export default App;

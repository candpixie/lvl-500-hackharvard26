import '@fontsource-variable/jost'
import '@fontsource-variable/geist'
import './home.css'

export default function Research({ onBack }: { onBack: () => void }) {
  return (
    <main className="home">
      <header className="home-top">
        <button type="button" className="home-link" onClick={onBack}>
          ← lvl 500
        </button>
      </header>
      <section className="home-hero">
        <p className="home-kicker">Research &amp; Sustainability</p>
        <h1 className="home-title research-title">Coming soon</h1>
        <p className="home-lede">
          This page will cover the research on moving data infrastructure into space and what it could mean
          for climate impact on Earth.
        </p>
      </section>
      <footer className="home-foot" />
    </main>
  )
}

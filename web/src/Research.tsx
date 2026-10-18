import '@fontsource-variable/jost'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import Stars from './Stars.tsx'
import './home.css'

const shells = [
  {
    index: '01',
    title: 'Close approaches',
    body: 'Objects already pass within meters of each other at several kilometers per second. A miss is a warning. A hit does not stop at one satellite. It becomes fragments on new paths.',
  },
  {
    index: '02',
    title: 'One breakup feeds the next',
    body: 'Fragments raise the chance of the next strike. That cascade, often called Kessler syndrome, can turn a useful shell into a debris field and close it for decades.',
  },
  {
    index: '03',
    title: 'What stays up, and what comes down',
    body: 'Junk in the higher shells can linger for a century or more. What eventually reenters does so without a controlled landing. The harm starts in orbit and can end on the ground.',
  },
]

export default function Research({ onBack }: { onBack: () => void }) {
  return (
    <main className="home research">
      <Stars className="research-sky" />
      <div className="research-orbits" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <header className="home-top research-top">
        <button type="button" className="home-link" onClick={onBack}>
          ← lvl 500
        </button>
        <span className="research-alt">500 km</span>
      </header>

      <article className="research-body">
        <p className="home-kicker">Research &amp; Sustainability</p>
        <h1 className="research-title">Keep the road off Earth open.</h1>
        <p className="research-lede">
          Sustainability is usually a story about the ground. This one is about the sky we have to cross
          to leave it. Low Earth orbit is a shared road with a finite number of lanes. Fill them without
          looking, and the next launch has nowhere safe to go.
        </p>

        <section className="research-mission">
          <p className="research-label">Mission</p>
          <p>
            lvl 500 is a pre-launch check for orbital crowding. Pick what you are sending up and where.
            We place it among tracked satellites and debris, show how long a dead object would stay, and
            point you toward a quieter shell before it ever leaves the ground.
          </p>
        </section>

        <section>
          <p className="research-label">The problem</p>
          <h2>Space clustering is a sustainability problem.</h2>
          <p className="research-copy">
            About 29,000 objects are tracked in orbit today. Working satellites already pack the low
            shells. Debris piles up higher, where air drag is too weak to clear it. Proposals on file
            would add far more — including up to a million orbital data-center satellites. The question
            is no longer whether we launch. It is whether the altitude we pick can still absorb what we
            send.
          </p>
          <div className="research-grid">
            {shells.map((shell) => (
              <article key={shell.index}>
                <span className="research-index">{shell.index}</span>
                <h3>{shell.title}</h3>
                <p>{shell.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section>
          <p className="research-label">Why this matters</p>
          <h2>Prevention happens before launch.</h2>
          <p className="research-copy">
            A shell lost to debris is a resource we do not get back on a human timescale: launch access,
            communications, Earth observation, and every mission that needed that altitude. The lever is
            the decision made on the ground. Choose a quieter orbit, and you lower the chance of the
            cascade before the object is even up there.
          </p>
          <ul className="research-points">
            <li>
              <strong>Low shells are crowded with working satellites.</strong> Around 450 to 500 km,
              roughly 10,000 tracked objects, mostly active constellations. Drag clears dead ones within
              years, but only if we do not keep packing the lane.
            </li>
            <li>
              <strong>Higher shells keep the junk.</strong> Around 750 to 850 km, a few thousand tracked
              objects are mostly debris. Nature will not sweep that lane clean.
            </li>
            <li>
              <strong>The map is a lower bound.</strong> We draw from CelesTrak SATCAT and SOCRATES close
              approaches. Tracked objects only — the real neighborhood is busier than the picture.
            </li>
          </ul>
        </section>

        <div className="research-actions">
          <button type="button" className="home-start" onClick={onBack}>
            Back to lvl 500
          </button>
        </div>
      </article>
    </main>
  )
}

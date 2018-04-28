import React, { Component } from 'react';
import './App.css';
import { get, post } from 'axios';

const debounce = (fn, delay) => {
      let timer = null;
      return function (...args) {
          const context = this;
          timer && clearTimeout(timer);
          timer = setTimeout(() => {
              fn.apply(context, args);
          }, delay);
      };
}

const suggestHostname = (name) => {
    name = name.toLowerCase();
    name = name.replace(/^\-+/, '');
    name = name.replace(/[^a-z\s-]/g, '');
    name = name.replace(/\s+/g, '-');
    return name + '-near-me';
}

class App extends Component {
    state = {
        places: [],
        q: '',
        plural: null,
        hostname: null,
        speciesList: [],
        speciesInfo: null,
        speciesLoading: false,
        taxonId: null,
        publishing: false,
        deploy_url: null,
        deploy_message: null,
    }
    constructor(props) {
        super(props);
        this.searchSpecies = debounce(this.searchSpecies, 200);
    }
    onTextChange(ev) {
        this.setState({
            q: ev.target.value
        });
        this.searchSpecies(ev.target.value);
    }
    onPluralTextChange(ev) {
        this.setState({
            plural: ev.target.value
        });
    }
    onHostnameTextChange(ev) {
        this.setState({
            hostname: ev.target.value
        });
    }
    searchSpecies(q) {
        this.setState({speciesLoading: true});
        get('https://api.inaturalist.org/v1/taxa/autocomplete', {
            params: {q}
        }).then(response => {
            this.setState({
                speciesList: response.data.results,
                speciesLoading: false
            });
        });
    }
    fetchSpecies(id) {
        get(`https://api.inaturalist.org/v1/taxa/${id}`).then(response => {
            const info = response.data.results[0];
            this.setState({
                speciesInfo: info,
                speciesLoading: false,
                speciesList: [],
                plural: info.preferred_common_name || info.name,
                hostname: null,
                taxonId: info.id,
            });
        });
    }
    onSearchSubmit(ev) {
        ev.preventDefault();
    }
    onPublishSubmit(ev) {
        ev.preventDefault();
        const info = this.state.speciesInfo;
        const name = info.preferred_common_name || info.name;
        post('/publish', {
            taxon_id: this.state.taxonId,
            taxon_plural: this.state.plural,
            hostname: this.state.hostname || suggestHostname(
                this.state.plural || name
            ),
        }, {
            headers: {
                'content-type': 'application/json'
            }
        }).then(response => {
            if (response.data.ok) {
                this.setState({
                    deploy_url: `https://${response.data.deploy_url}`,
                    deploy_message: response.data.deploy_message,
                    publishing: false
                });
            } else {
                alert(response.data.msg);
            }
        }).catch(err => {
            alert(err);
        });
    }
    render() {
        const info = this.state.speciesInfo;
        const name = info ? (info.preferred_common_name || info.name) : null;
        const suggested_hostname = (
            info ? (this.state.hostname || suggestHostname(this.state.plural || name)) : null
        );
        return (
            <div>
                <section className="primary">
                    <div className="inner">
                        <h1>Make Near Me</h1>
                        <div className="intro-text">
                            <p>Make <a href="https://www.owlsnearme.com/" target="_blank">Owls Near Me</a> for the species of your choice!</p>
                        </div>
                        {this.state.publishing && <h1>PUBLIHING</h1>}
                        <form action="/" method="GET" onSubmit={this.onSearchSubmit.bind(this)}>
                            <div className="search-form">
                                <label><span>Search for a species</span><input
                                    type="text"
                                    size={30}
                                    title="Location"
                                    className="text"
                                    name="q"
                                    onChange={this.onTextChange.bind(this)}
                                    placeholder="Search for a species"
                                    value={this.state.q || ''}
                                    autoComplete="off"
                                /></label>
                                <button type="submit" className="submit">Go</button>
                                {this.state.speciesList.length !== 0 && <div className="search-suggest">
                                    {this.state.speciesList.map(species => {
                                        return <div key={species.id}>
                                            <a onClick={(ev) => {
                                                ev.preventDefault();
                                                this.fetchSpecies(species.id);
                                            }} target="_blank" href={`https://www.owlsnearme.com/?taxon_id=${species.id}`}>{species.preferred_common_name || species.name}</a>
                                            <em> - {species.name}</em>
                                        </div>
                                    })}
                                </div>}
                                {this.state.speciesLoading && <LoadingDots fill="#B04C5E" style={{
                                    position: 'absolute',
                                    top: '0.6rem',
                                    right: '3rem',
                                    height: '1rem'
                                }} />}
                            </div>
                            <pre style={{display: 'none', color: 'white'}}>{JSON.stringify(this.state.speciesList, null, 2)}</pre>
                        </form>
                        {info && <div>
                            <h2>{info.preferred_common_name || info.name}</h2>
                            <p>{info.ancestors.map((a => <span key={a.id}>&nbsp;&middot;&nbsp;<a
                                onClick={(ev) => {
                                    ev.preventDefault();
                                    this.fetchSpecies(a.id);
                                }} target="_blank" href={`https://www.owlsnearme.com/?taxon_id=${a.id}`}
                            >{a.preferred_common_name || a.name}
                            </a></span>))}</p>
                            <form action="/" method="POST" onSubmit={this.onPublishSubmit.bind(this)}>
                                <label htmlFor="input-plural" className="big-label">Plural to use</label>
                                <input type="text"
                                    id="input-plural"
                                    value={this.state.plural}
                                    onChange={this.onPluralTextChange.bind(this)}
                                    style={{width: '100%'}}/>
                                <label htmlFor="input-hostname" className="big-label">Site URL (<samp>X.now.sh</samp>)</label>
                                <input type="text"
                                    id="input-hostname"
                                    value={suggested_hostname}
                                    onChange={this.onHostnameTextChange.bind(this)}
                                    style={{width: '100%'}}
                                />
                                <button type="submit" className="submit">Publish</button>
                            </form>
                        </div>}
                        {this.state.deploy_url && <p><a href={this.state.deploy_url}>{this.state.deploy_url}</a></p>}
                    </div>

                </section>
                <section className="footer">
                    <div className="inner">
                        <p className="meta">by <a href="https://twitter.com/natbat">Natalie Downe</a> and <a href="https://twitter.com/simonw">Simon Willison</a> using data from <a href="https://www.inaturalist.org/">iNaturalist</a> - <a href="https://github.com/simonw/owlsnearme">README</a></p>
                    </div>
                </section>
            </div>
        );
    }
}

export default App;



const LoadingDots = (props) => {
    // Adapted from http://samherbert.net/svg-loaders/ by @samh
    return (
        <svg style={props.style} width={props.width || 120} height={props.height || 30} viewBox="0 0 120 30" fill={props.fill || '#fff'}>
            <circle cx="15" cy="15" r="15">
              <animate attributeName="r" from="15" to="15"
                       begin="0s" dur="0.8s"
                       values="15;9;15" calcMode="linear"
                       repeatCount="indefinite" />
              <animate attributeName="fill-opacity" from="1" to="1"
                       begin="0s" dur="0.8s"
                       values="1;.5;1" calcMode="linear"
                       repeatCount="indefinite" />
            </circle>
            <circle cx="60" cy="15" r="9" fillOpacity="0.3">
              <animate attributeName="r" from="9" to="9"
                       begin="0s" dur="0.8s"
                       values="9;15;9" calcMode="linear"
                       repeatCount="indefinite" />
              <animate attributeName="fill-opacity" from="0.5" to="0.5"
                       begin="0s" dur="0.8s"
                       values=".5;1;.5" calcMode="linear"
                       repeatCount="indefinite" />
            </circle>
            <circle cx="105" cy="15" r="15">
              <animate attributeName="r" from="15" to="15"
                       begin="0s" dur="0.8s"
                       values="15;9;15" calcMode="linear"
                       repeatCount="indefinite" />
              <animate attributeName="fill-opacity" from="1" to="1"
                       begin="0s" dur="0.8s"
                       values="1;.5;1" calcMode="linear"
                       repeatCount="indefinite" />
            </circle>
        </svg>
    );
}

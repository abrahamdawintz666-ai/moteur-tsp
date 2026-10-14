    <script>
        let langueActuelle = 'FR';
        
        const outils = {
            'FR': [
                { nom: '📱 Bouton', code: 'bouton mon_bouton [texte: "Mettre en vente", couleur: Vert] .' },
                { nom: '📝 Texte', code: 'affichage_texte statut [contenu: "Bienvenue"] .' },
                { nom: '📥 Saisie', code: 'zone_saisie formulaire [indication: "Entrez votre nom"] .' },
                { nom: '🔒 Sécurité', code: 'securite: "admin123" .' },
                { nom: '⚡ Bloc Action', code: 'quand mon_bouton fait cliquer ->\n    \n.' }
            ],
            'EN': [
                { nom: '📱 Button', code: 'button my_button [text: "Submit", color: Blue] .' },
                { nom: '📝 Text', code: 'text_display status [content: "Welcome"] .' },
                { nom: '📥 Input', code: 'input_field form [indication: "Your name"] .' },
                { nom: '🔒 Security', code: 'security: "admin123" .' },
                { nom: '⚡ Action Block', code: 'when my_button does click ->\n    \n.' }
            ]
        };

        const textesUI = {
            'FR': { editor: 'Zone de Code BuKo :', preview: 'APERCU EN DIRECT', gen: 'Générer mon Application', ph: 'Écrivez votre logique ici... N\'oubliez pas le point classique \'.\' en fin de ligne !' },
            'EN': { editor: 'BuKo Code Area:', preview: 'LIVE PREVIEW', gen: 'Generate my Application', ph: 'Write your logic here... Don\'t forget the classic dot \'.\' at the end of the line!' }
        };

        function chargerBoiteOutils() {
            const box = document.getElementById('toolbox');
            box.innerHTML = '';
            outils[langueActuelle].forEach(outil => {
                let btn = document.createElement('button');
                btn.className = 'tool-btn';
                btn.innerText = outil.nom;
                btn.onclick = () => insererCode(outil.code);
                box.appendChild(btn);
            });
        }

        function toggleLangue() {
            langueActuelle = (langueActuelle === 'FR') ? 'EN' : 'FR';
            document.getElementById('langBtn').innerText = '🌐 ' + langueActuelle;
            document.getElementById('lblEditor').innerText = textesUI[langueActuelle].editor;
            document.getElementById('lblPreview').innerText = textesUI[langueActuelle].preview;
            document.getElementById('btnGen').innerText = textesUI[langueActuelle].gen;
            document.getElementById('codeEditor').placeholder = textesUI[langueActuelle].ph;
            chargerBoiteOutils();
        }

        function insererCode(code) {
            const editor = document.getElementById('codeEditor');
            editor.value += (editor.value.endsWith('\n') || editor.value === '' ? '' : '\n') + code + '\n';
            compilerBuKo();
        }

        function compilerBuKo() {
            const code = document.getElementById('codeEditor').value;
            const canvas = document.getElementById('canvas');
            canvas.innerHTML = ''; 

            const lignes = code.split('\n');

            lignes.forEach(ligne => {
                let l = ligne.trim();
                if (!l.endsWith('.')) return;
                l = l.slice(0, -1).trim(); 

                if (l.startsWith('[') && l.endsWith(']')) {
                    let titreSpace = document.createElement('div');
                    titreSpace.className = 'buko-space-title';
                    titreSpace.innerText = l.slice(1, -1);
                    canvas.appendChild(titreSpace);
                }

                const matchComp = l.match(/^(\w+)\s+(\w+)\s*\[(.*)\]\$/);
                if (matchComp) {
                    const type = matchComp[1].toLowerCase();
                    const optionsBrutes = matchComp[3];
                    
                    let options = {};
                    optionsBrutes.split(',').forEach(part => {
                        if (part.includes(':')) {
                            let [k, v] = part.split(':');
                            options[k.trim()] = v.trim().replace(/"/g, '');
                        }
                    });

                    if (type === 'bouton' || type === 'button') {
                        let btn = document.createElement('button');
                        let couleur = options.couleur || options.color || 'Standard';
                        btn.className = `buko-btn ${couleur}`;
                        btn.innerText = options.texte || options.text || '[Button]';
                        if (options.animation === 'Secouer' || options.animation === 'Shake') {
                            btn.classList.add('Secouer');
                        }
                        canvas.appendChild(btn);
                    } 
                    else if (type === 'affichage_texte' || type === 'text_display') {
                        let txt = document.createElement('div');
                        txt.className = 'buko-text';
                        txt.innerText = options.contenu || options.content || '';
                        canvas.appendChild(txt);
                    }
                    else if (type === 'zone_saisie' || type === 'input_field') {
                        let inp = document.createElement('input');
                        inp.className = 'buko-input';
                        inp.type = 'text';
                        inp.placeholder = options.indication || '';
                        canvas.appendChild(inp);
                    }
                }
            });
        }

        chargerBoiteOutils();
    </script>
</body>
</html>

// Palet SakuKu: "kertas buku kas" — krem hangat, hijau pine, terracotta, ochre.
// Satu sumber untuk semua halaman (index, admin, auth).
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Instrument Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['"Bricolage Grotesque"', '"Instrument Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        white: '#FFFEFB',
        // Netral hangat (menggantikan slate biru-dingin)
        slate: {
          50: '#F6F3EC', 100: '#EEEAE0', 200: '#E3DDCF', 300: '#CFC7B5', 400: '#8B8272',
          500: '#6B6354', 600: '#544D40', 700: '#3B362C', 800: '#2A2620', 900: '#1D1A16', 950: '#14120F',
        },
        // Merek: hijau pine
        brand: {
          50: '#EBF3EE', 100: '#D6E7DD', 200: '#B3D3C1', 300: '#8CBFA3', 400: '#5FA282',
          500: '#3A8566', 600: '#1F5B47', 700: '#194A3A', 800: '#143B2E', 900: '#0F2D23',
        },
        // Pemasukan: hijau daun
        emerald: {
          50: '#EDF5E8', 100: '#DCEBD2', 200: '#BDD9AE', 300: '#98C387', 400: '#72AB60',
          500: '#4E9040', 600: '#3B7A32', 700: '#2F6128', 800: '#264E22', 900: '#1C3A19',
        },
        // Pengeluaran: terracotta
        rose: {
          50: '#FCEFEA', 100: '#F8DDD3', 200: '#F0BEAD', 300: '#E59C84', 400: '#D97A5C',
          500: '#C85E3F', 600: '#B1472B', 700: '#903821', 800: '#702D1B', 900: '#4F2014',
        },
        // Peringatan / aksen: ochre
        amber: {
          50: '#FBF4E1', 100: '#F5E6BE', 200: '#EBD08A', 300: '#E0B85A', 400: '#D2A03A',
          500: '#BC8628', 600: '#98681A', 700: '#7A5216', 800: '#5E4014', 900: '#442E0F',
        },
      },
    },
  },
};

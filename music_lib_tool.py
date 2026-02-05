from tinytag import TinyTag
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import subprocess
import sys
import json
import re
from multiprocessing import Pool
from tqdm import tqdm

# Validation of the music tags
def library_validator(library_path):
	allowed_categories = {
		'comment' : ['Known', 'French', 'Spanish', 'Russian', 'Finnish', 'German', 'Japanese', 'Irish', 'Portuguese', 'Kid', 'Comedy', 'Instrumental', 'Live'],
		'genre' : ['Pop', 'Pop/Rock', 'Pop/Dance', 'Pop/Country', 'Pop/Classic', 'Ballad', 'Electro', 'Bluegrass', 'Traditional', 'Hard Rock', 'Hip-Hop/Rap', 'Indie/Folk', 'Classical', 'Orchestral', 'Military', 'Other'],
		'txxx:musicbrainz album type': ['Album', 'Single', 'EP', 'Compilation', 'Soundtrack']

	}

	warnings = defaultdict(list)
	errors = defaultdict(list)

	for root, _, files in tqdm(library_path.walk(), desc='Validating Files'):
		for name in files:
			file_path = (root / name)

			# Ignore the file if TinyTag can't read tags
			if not TinyTag.is_supported(str(file_path)):
				print(f'File {str(file_path)} is not supported by TinyTag')
				continue

			# Cover Art
			tag_img = TinyTag.get(str(file_path), image=True)

			# if there is a cover art but it's not tagged as 'front cover'
			if tag_img.images.front_cover is None:
				if tag_img.images.any is not None:
					errors[str(file_path)].append(f'Has a Cover Art, but missidentified as {tag_img.images.any.name}')

			# Other tags (not images)
			tag_dict = TinyTag.get(str(file_path)).as_dict()

			# Check that the tags that should exist do exist
			for tag in ['album', 'albumartist', 'artist', 'genre', 'title', 'track', 'txxx:musicbrainz album type']:
				if tag not in tag_dict.keys():
					errors[str(file_path)].append(f'{tag} is missing')

			# Check that the tags that should be a list containing a single non-empty string are just that
			for tag in ['album', 'albumartist', 'artist', 'comment', 'genre', 'title', 'year', 'txxx:musicbrainz album type']:
				if tag not in tag_dict.keys():
					continue
				try:
					if len(tag_dict[tag][0]) == 0:
						errors[str(file_path)].append(f'{tag} is an empty string.')
				except Exception as e:
					errors[str(file_path)].append(f'{tag} is not a list containing a single string: {tag_dict[tag]}')

			# Check that the categorical tags only contain categoies
			for tag, allowed_words in allowed_categories.items():
				if tag not in tag_dict.keys():
					continue
				for word in tag_dict[tag][0].split(';'):
					if word.strip() not in allowed_words:
						errors[str(file_path)].append(f'{tag} is a categorical tag with the unknown word {word.strip()}')

			# Check that track and disc are not 0 and that if a total exist, it is superior or equal to the tag
			for tag, tag_total in [('track', 'track_total'), ('disc', 'disc_total')]:
				if tag not in tag_dict.keys():
					if tag_total in tag_dict.keys():
						errors[str(file_path)].append(f'{tag} is missing but {tag_total} is set ({tag_dict[tag_total]})')
					continue
				if tag_dict[tag] == 0:
					errors[str(file_path)].append(f'{tag} is zero')
				if tag_total in tag_dict.keys() and tag_dict[tag] > tag_dict[tag_total]:
					errors[str(file_path)].append(f'{tag} > {tag_total} ({tag_dict[tag]} > {tag_dict[tag_total]})')

			# Check that year is a numeric string corresponding to a number between 1000 and current year
			if 'year' in tag_dict.keys():
				try:
					year = int(tag_dict['year'][0])
					if year < 1000 or year > datetime.now().year:
						errors[str(file_path)].append(f'year is outside of bounds: {tag_dict['year']}')
				except Exception as e:
					errors[str(file_path)].append(f'year is malformed: {tag_dict['year']}')

	if len(errors.keys()) > 0:
		print('ERRORS:')
		for file in errors.keys():
			print(file)
			for error in errors[file]:
				print(error)

		return False

	return True

# Returns a set of all the music files supported by TinyTag in the path, optionally only the one that contain 'Known' in the comment
def list_files(path, known=False):
	all_files = set()

	for root, _, files in path.walk():
		for name in files:
			file_path = (root / name)
			if not TinyTag.is_supported(str(file_path)):
				continue

			if not known:
				all_files.add(file_path.relative_to(path))
				continue

			tags = TinyTag.get(str(file_path))
			if tags.comment is not None and 'Known' in tags.comment:
				all_files.add(file_path.relative_to(path))

	return all_files

# Returns a dict of four lists of path to music files relative to library : [Known, Kid, Russian and Latest50]
def _get_playlists(library, destination):
	playlists = defaultdict(list)
	known_files = list(list_files(library, known=True))

	for file in known_files:
		# Those all have at least 'Known' in comment tag
		tags = TinyTag.get(str(library / file))
		file_path = (library / file).relative_to(library)

		# Everything
		playlists['Everything'].append(file_path)

		# Work
		if 'Kid' not in tags.comment:
			playlists['Work'].append(file_path)

		# Russian
		if 'Russian' in tags.comment:
			playlists['Russian'].append(file_path)

		# Latest50
		mod_date = (library / file).stat().st_ctime
		if len(playlists['Latest50']) < 50 or mod_date > playlists['Latest50'][-1][1]:
			playlists['Latest50'].append((file_path, mod_date))
			playlists['Latest50'] = sorted(playlists['Latest50'], key=lambda x: x[1], reverse=True)[:50]

	playlists['Latest50'] = [x[0] for x in playlists['Latest50']]

	return playlists

# Gets playlists dict from _get_playlists(), and write those as .m3u playlist files
def make_playlists(library, destination):
	playlists = _get_playlists(library, destination)

	# For computer and phone
	for path in [library, destination]:
		playlists_path = path / 'Playlists'

		# Create destination arborescence if necessary
		playlists_path.mkdir(parents=True, exist_ok=True)

		# For each playlist
		for playlist_name in playlists.keys():
			playlist_path = playlists_path / (playlist_name + '.m3u')

			with open(playlist_path, 'w', encoding='utf-8') as f:

				# For each music file path
				for file in playlists[playlist_name]:
					suffix = '.mp3' if path == destination else file.suffix
					file_path = '..' / file.with_suffix(suffix)
					f.write(str(file_path) + '\n')

# Transcode and Loudnorm a single music file
# TODO: Use opus if/when cover art integration is correctly handled in ffmpeg
def process_file(args):
	path, library, destination = args

	old_path = library / path
	new_path = destination / path.with_suffix('.mp3')

	# Create destination arborescence if necessary
	new_path.parent.mkdir(parents=True, exist_ok=True)

	# First Pass : compute loudnorm params
	# ffmpeg -hide_banner -i 'input.ext' -filter:a 'loudnorm=print)format=json' -f null -
	cmd1 = [
		'ffmpeg', '-hide_banner',
		'-i', str(old_path),
		'-filter:a', 'loudnorm=print_format=json', 
		'-f', 'null', '-'
	]

	# Extract json params from cluttered ffmpeg output
	proc = subprocess.run(cmd1, stderr=subprocess.PIPE, text=True)
	stderr = proc.stderr
	match = re.search(r'\{[\s\S]*\}', stderr)
	loudnorm_data  = json.loads(match.group(0))

	loudnorm_params = {
		'i': -12,
		'lra': 14,
		'tp': -1,
		'measured_i': loudnorm_data['input_i'],
		'measured_lra': loudnorm_data['input_lra'],
		'measured_tp': loudnorm_data['input_tp'],
		'offset': loudnorm_data['target_offset']
	}

	# Second Pass: actually transcode the music file
	# ffmpeg -y -hide_banner -loglevel error -i 'input.ext' -c:a libmp3lame -q:a 2 -ar 48000 -ac 2 -filter:a 'loudnorm=linear=true:i=-xx:lra=xx:tp=-x:measured_i=-x.x:measured_lra=x.x:measured_tp=x.xx:offset=-x.xx' 'output.mp3'
	cmd2 = [
		'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
		'-i', str(old_path),
		'-c:a', 'libmp3lame', '-q:a', '2',
		'-ar', '48000', '-ac', '2',
		'-filter:a', 'loudnorm=linear=true:' + ':'.join(f'{k}={v}' for k, v in loudnorm_params.items()),
		str(new_path)
	]

	# print(' '.join(cmd2))

	subprocess.run(cmd2, stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr)

# Parallel execution of process_file for each file in file_list
def process_all_files(file_list, library, destination):
	args = [(Path(f), library, destination) for f in file_list]

	with Pool(12) as p:
		for _ in tqdm(p.imap_unordered(process_file, args), total=len(args), desc='Processing Files'):
			pass

# Main
if __name__ == '__main__':

	LIBRARY = '/media/greyecho/grey/Music'
	DESTINATION = '/media/greyecho/grey/Music/Phone/Music'

	input_library_path = Path(LIBRARY) / 'Library'
	input_root_path = Path(LIBRARY)
	output_library_path = Path(DESTINATION) / 'Library'
	output_root_path = Path(DESTINATION)

	# Validation of the music tags
	valid = library_validator(input_library_path)

	if valid:
		input_files = list_files(input_library_path, known=True)
		input_files_no_suffix = {Path(f).with_suffix('') for f in input_files}
		output_files_no_suffix = {Path(f).with_suffix('') for f in list_files(output_library_path)}

		# Files to process are all the known files in input, except those that are already in output
		files_to_process_no_suffix = input_files_no_suffix - output_files_no_suffix
		files_to_process = [f for f in input_files if Path(f).with_suffix('') in files_to_process_no_suffix]

		# Transcode
		process_all_files(files_to_process, input_library_path, output_library_path)

		# Playlists Generation
		make_playlists(input_root_path, output_root_path)

